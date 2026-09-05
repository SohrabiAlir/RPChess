import os
import chess
import chess.svg
import random
import time
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from threading import Lock

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Game state
waiting_player = None
games = {}
game_id_counter = 0
lock = Lock()

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    global waiting_player
    with lock:
        if waiting_player and waiting_player[0] == request.sid:
            waiting_player = None
        
        for game_id, game in list(games.items()):
            if game['white'] == request.sid or game['black'] == request.sid:
                opponent_sid = game['black'] if game['white'] == request.sid else game['white']
                socketio.emit('opponent_left', room=opponent_sid)
                save_game_log(game_id)
                del games[game_id]
                break

@socketio.on('join')
def handle_join(data):
    global waiting_player, game_id_counter
    nickname = data.get('nickname', 'Anonymous')
    
    print(f"📥 Join request from: {nickname}")
    
    with lock:
        if waiting_player:
            player1_sid, player1_name = waiting_player
            player2_sid = request.sid
            
            game_id = game_id_counter
            game_id_counter += 1
            
            if random.random() < 0.5:
                white_sid, black_sid = player1_sid, player2_sid
                white_name, black_name = player1_name, nickname
            else:
                white_sid, black_sid = player2_sid, player1_sid
                white_name, black_name = nickname, player1_name
            
            games[game_id] = {
                'white': white_sid,
                'black': black_sid,
                'white_name': white_name,
                'black_name': black_name,
                'board': chess.Board(),
                'log': [],
                'turn': chess.WHITE,
                'move_count': 0
            }
            
            join_room(str(game_id))
            waiting_player = None
            
            # Generate board SVG from BOTH perspectives
            board_svg_white = chess.svg.board(games[game_id]['board'], size=400, orientation=chess.WHITE)
            board_svg_black = chess.svg.board(games[game_id]['board'], size=400, orientation=chess.BLACK)
            
            print(f"🎮 Game {game_id} started: {white_name} (White) vs {black_name} (Black)")
            
            # Send to White player with White's perspective
            socketio.emit('game_start', {
                'game_id': game_id,
                'color': 'white',
                'opponent': black_name,
                'board_svg': board_svg_white,
                'message': f"You are White against {black_name}"
            }, room=white_sid)
            
            # Send to Black player with Black's perspective
            socketio.emit('game_start', {
                'game_id': game_id,
                'color': 'black',
                'opponent': white_name,
                'board_svg': board_svg_black,
                'message': f"You are Black against {white_name}"
            }, room=black_sid)
            
        else:
            waiting_player = (request.sid, nickname)
            print(f"⏳ {nickname} added to waiting queue")
            emit('waiting', {'message': f"Waiting for opponent, {nickname}..."})

@socketio.on('move')
def handle_move(data):
    game_id = data.get('game_id')
    move_san = data.get('move', '').strip()
    
    print(f"Received move: '{move_san}' from {request.sid}")
    
    if game_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    if not move_san:
        emit('error', {'message': 'Please enter a move (e.g., Nf3, exd5, O-O)'})
        return
    
    game = games[game_id]
    board = game['board']
    
    # Check if it's this player's turn
    sid = request.sid
    if game['turn'] == chess.WHITE and sid != game['white']:
        emit('error', {'message': 'Not your turn! (White)'})
        return
    if game['turn'] == chess.BLACK and sid != game['black']:
        emit('error', {'message': 'Not your turn! (Black)'})
        return
    
    # Parse algebraic notation
    try:
        move = board.parse_san(move_san)
        print(f"Parsed move: {move}")
    except ValueError as e:
        print(f"Parse error: {e}")
        emit('error', {'message': f'Invalid algebraic notation: "{move_san}". Use e.g., Nf3, exd5, O-O'})
        return
    
    # Check if move is pseudo-legal (RPChess)
    if move not in board.pseudo_legal_moves:
        emit('error', {'message': f'Illegal move: {move_san}'})
        return
    
    # Make the move
    captured_piece = board.piece_at(move.to_square)
    board.push(move)
    game['move_count'] += 1
    
    # Get SAN representation
    try:
        san = board.san(move)
    except:
        san = move_san
    
    # Log the move
    game['log'].append({
        'move_number': game['move_count'],
        'move': move.uci(),
        'san': san,
        'player': 'White' if game['turn'] == chess.WHITE else 'Black',
        'captured': str(captured_piece) if captured_piece else None
    })
    
    # Check for king capture (RPChess win condition)
    if captured_piece and captured_piece.piece_type == chess.KING:
        winner = 'White' if game['turn'] == chess.WHITE else 'Black'
        save_game_log(game_id)
        del games[game_id]
        socketio.emit('game_over', {
            'winner': winner,
            'message': f'🏆 {winner} captured the enemy king! Game Over!'
        }, room=str(game_id))
        return
    
    # Coin toss for next turn
    coin = random.randint(0, 1)
    next_turn = chess.WHITE if coin == 0 else chess.BLACK
    
    # Update BOTH the game state AND the board object
    game['turn'] = next_turn
    board.turn = next_turn
    
    next_player = 'White' if next_turn == chess.WHITE else 'Black'
    
    # Generate board SVG from BOTH perspectives
    board_svg_white = chess.svg.board(board, size=400, orientation=chess.WHITE)
    board_svg_black = chess.svg.board(board, size=400, orientation=chess.BLACK)
    
    # Broadcast update to White player with White's perspective
    socketio.emit('board_update', {
        'board_svg': board_svg_white,
        'turn': next_player,
        'last_move': san,
        'message': f"Coin toss: {coin} -> {next_player}'s turn!"
    }, room=game['white'])
    
    # Broadcast update to Black player with Black's perspective
    socketio.emit('board_update', {
        'board_svg': board_svg_black,
        'turn': next_player,
        'last_move': san,
        'message': f"Coin toss: {coin} -> {next_player}'s turn!"
    }, room=game['black'])

def save_game_log(game_id):
    if game_id not in games:
        return
    
    game = games[game_id]
    board = game['board']
    
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    
    if white_king is None:
        winner = 'Black'
    elif black_king is None:
        winner = 'White'
    else:
        winner = 'Incomplete'
    
    filename = f"games/game_{game_id}_{int(time.time())}.txt"
    os.makedirs('games', exist_ok=True)
    
    with open(filename, 'w') as f:
        f.write(f"RPChess Game #{game_id}\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"White: {game['white_name']}\n")
        f.write(f"Black: {game['black_name']}\n")
        f.write(f"Winner: {winner}\n")
        f.write(f"Total Moves: {game['move_count']}\n")
        f.write("-" * 60 + "\n")
        f.write("Move Log:\n")
        for entry in game['log']:
            move_num = entry['move_number']
            player = entry['player']
            san = entry['san']
            captured = f" (captures {entry['captured']})" if entry.get('captured') else ""
            f.write(f"{move_num:3d}. {player:5s}: {san}{captured}\n")
        f.write("-" * 60 + "\n")
        f.write(f"Final Position FEN:\n{board.fen()}\n")

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    os.makedirs('games', exist_ok=True)
    print("♟️ RPChess Server Starting...")
    print("📡 Listening on http://0.0.0.0:5005")
    socketio.run(app, host='0.0.0.0', port=5005, debug=True)