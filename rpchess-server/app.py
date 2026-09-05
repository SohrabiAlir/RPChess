import os
import chess
import chess.engine
import random
import time
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from threading import Lock

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Stockfish path (adjust for your server)
STOCKFISH_PATH = "/usr/games/stockfish"
engine = None

# Load Stockfish if available
try:
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    print("Stockfish loaded successfully!")
except:
    print("Warning: Stockfish not found - AI features will be unavailable")
    engine = None

# Game state
waiting_player = None  # (sid, nickname)
games = {}  # game_id -> {'white': sid, 'black': sid, 'board': chess.Board(), 'log': []}
game_id_counter = 0
lock = Lock()

# Import your RPChess functions (adapt as needed)
def evaluate_board(board):
    """Simple material evaluation (copy from your bots.py)"""
    if board.king(chess.WHITE) is None:
        return -1000000
    if board.king(chess.BLACK) is None:
        return 1000000
    
    piece_values = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 20000
    }
    
    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            value = piece_values.get(piece.piece_type, 0)
            score += value if piece.color == chess.WHITE else -value
    return score

def get_best_move(board, engine):
    """Get best move using Stockfish"""
    if not engine:
        return None
    try:
        analysis_board = board.copy(stack=False)
        analysis_board.clear_stack()
        result = engine.analyse(analysis_board, chess.engine.Limit(time=0.5))
        pv = result.get("pv")
        if pv:
            return pv[0]
        return None
    except:
        return None

# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    global waiting_player
    with lock:
        # Remove from waiting
        if waiting_player and waiting_player[0] == request.sid:
            waiting_player = None
        
        # Remove from games
        for game_id, game in list(games.items()):
            if game['white'] == request.sid or game['black'] == request.sid:
                # Notify other player
                opponent_sid = game['black'] if game['white'] == request.sid else game['white']
                socketio.emit('opponent_left', room=opponent_sid)
                # Save game log if incomplete
                save_game_log(game_id)
                del games[game_id]
                break

@socketio.on('join')
def handle_join(data):
    global waiting_player, game_id_counter
    nickname = data.get('nickname', 'Anonymous')
    
    with lock:
        if waiting_player:
            # Match found!
            player1_sid, player1_name = waiting_player
            player2_sid = request.sid
            
            # Create new game
            game_id = game_id_counter
            game_id_counter += 1
            
            # Randomly assign colors
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
                'turn': chess.WHITE  # White always starts in standard chess
            }
            
            # Join both players to the game room
            join_room(str(game_id))
            
            # Clear waiting player
            waiting_player = None
            
            # Notify both players
            board_svg = chess.svg.board(games[game_id]['board'], size=400)
            socketio.emit('game_start', {
                'game_id': game_id,
                'color': 'white',
                'opponent': black_name,
                'board_svg': board_svg,
                'message': f"You are White against {black_name}"
            }, room=white_sid)
            
            socketio.emit('game_start', {
                'game_id': game_id,
                'color': 'black',
                'opponent': white_name,
                'board_svg': board_svg,
                'message': f"You are Black against {white_name}"
            }, room=black_sid)
            
            print(f"Game {game_id} started: {white_name} (White) vs {black_name} (Black)")
        else:
            # Put this player in waiting
            waiting_player = (request.sid, nickname)
            emit('waiting', {'message': f"Waiting for opponent, {nickname}..."})

@socketio.on('move')
def handle_move(data):
    game_id = data.get('game_id')
    move_uci = data.get('move')
    ai_move = data.get('ai', False)
    
    if game_id not in games:
        emit('error', {'message': 'Game not found'})
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
    
    # Parse move
    try:
        move = board.parse_uci(move_uci)
    except:
        emit('error', {'message': 'Invalid move format. Use UCI (e.g., e2e4)'})
        return
    
    # Check if move is pseudo-legal (RPChess)
    if move not in board.pseudo_legal_moves:
        emit('error', {'message': f'Illegal move: {move_uci}'})
        return
    
    # Make the move
    captured_piece = board.piece_at(move.to_square)
    board.push(move)
    
    # Log the move
    game['log'].append({
        'move': move_uci,
        'san': board.san(move) if board.san else move_uci,
        'player': 'White' if game['turn'] == chess.WHITE else 'Black',
        'captured': str(captured_piece) if captured_piece else None
    })
    
    # Check for king capture
    if captured_piece and captured_piece.piece_type == chess.KING:
        winner = 'White' if game['turn'] == chess.WHITE else 'Black'
        save_game_log(game_id, board, winner)
        del games[game_id]
        socketio.emit('game_over', {
            'winner': winner,
            'message': f'{winner} captured the enemy king!'
        }, room=str(game_id))
        return
    
    # Coin toss for next turn
    coin = random.randint(0, 1)
    next_turn = chess.WHITE if coin == 0 else chess.BLACK
    game['turn'] = next_turn
    next_player = 'White' if next_turn == chess.WHITE else 'Black'
    
    # Update board for both players
    board_svg = chess.svg.board(board, size=400)
    socketio.emit('board_update', {
        'board_svg': board_svg,
        'turn': next_player,
        'last_move': move_uci,
        'message': f"Coin toss: {coin} -> {next_player}'s turn!"
    }, room=str(game_id))

def save_game_log(game_id, board=None, winner=None):
    """Save game log to file"""
    if game_id not in games:
        return
    
    game = games[game_id]
    if board is None:
        board = game['board']
    
    if winner is None:
        winner = 'Incomplete'
    
    filename = f"games/game_{game_id}_{int(time.time())}.txt"
    os.makedirs('games', exist_ok=True)
    
    with open(filename, 'w') as f:
        f.write(f"RPChess Game #{game_id}\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"White: {game['white_name']}\n")
        f.write(f"Black: {game['black_name']}\n")
        f.write(f"Winner: {winner}\n")
        f.write("-" * 50 + "\n")
        f.write("Moves:\n")
        for i, entry in enumerate(game['log'], 1):
            player = entry['player']
            move_san = entry.get('san', entry['move'])
            captured = f" captures {entry['captured']}" if entry.get('captured') else ""
            f.write(f"{i:3d}. {player:5s}: {move_san}{captured}\n")
        f.write("-" * 50 + "\n")
        f.write(f"Final position FEN: {board.fen()}\n")

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # Create games directory
    os.makedirs('games', exist_ok=True)
    # Run the server
    socketio.run(app, host='0.0.0.0', port=5005, debug=True)