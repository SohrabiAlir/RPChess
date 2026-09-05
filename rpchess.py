import chess
import chess.engine
import random
import os
import chess.svg

# Global & Config

## Global engine variable (initialized once)
with open(os.path.join("stockfish", "stockfish_path.txt"), "r") as f:
    STOCKFISH_PATH = os.path.join("stockfish", f.read().strip())

AUTOGRAPH = True

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000
}

def evaluate_board(board):
    """Return a score from White's perspective (centipawns)."""
    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            value = PIECE_VALUES[piece.piece_type]
            if piece.color == chess.WHITE:
                score += value
            else:
                score -= value
    return score

def print_help():
    print("==================================================")
    print("               SPECIAL COMMANDS MENU              ")
    print("==================================================")
    print("  moves      : Print all pseudo-legal moves for both White and Black (SAN)")
    print("  random     : Play a random pseudo-legal move for the current player")
    print("  best       : Play the best move (uses Stockfish engine)")
    print("  evaluate   : Get Stockfish's evaluation of the current position (centipawns)")
    print("  expectimax : Play the best move using expectimax search (depth 2, Stockfish leaves)")
    print("  tree       : Show the move tree for 3 levels")
    print("  graph      : Save a graphical image of the board as 'board_image.svg'")
    print("  undo       : Undo the last move")
    print("  switch     : [Debug] Manually flip the turn to the other player")
    print("  exit       : Exit the game")
    print("  help       : Display this special commands menu again")
    print("  [move]     : Play a move using standard algebraic notation (e.g., e4, Nf3, O-O)")
    print("==================================================\n")

def get_san_moves(board):
    moves_san = []
    for move in board.pseudo_legal_moves:
        try:
            moves_san.append(board.san(move))
        except (ValueError, AssertionError):
            moves_san.append(move.uci())
    return moves_san

def print_all_moves(board):
    orig_turn = board.turn
    
    board.turn = chess.WHITE
    w_moves = get_san_moves(board)
    
    board.turn = chess.BLACK
    b_moves = get_san_moves(board)
    
    board.turn = orig_turn
    
    w_str = ", ".join(w_moves) if w_moves else "No moves available"
    b_str = ", ".join(b_moves) if b_moves else "No moves available"
    
    print(f"White moves: {w_str}")
    print(f"Black moves: {b_str}")

def get_stockfish_best_move(board, engine, time_limit=0.5):
    """
    Get Stockfish's best move from an arbitrary FEN position.
    First checks if the enemy king can be captured, then falls back to Stockfish.
    """
    
    # First, check if we can capture the enemy king
    enemy_king_square = board.king(not board.turn)
    if enemy_king_square:
        # Look through all pseudo-legal moves to see if any capture the enemy king
        for move in board.pseudo_legal_moves:
            if move.to_square == enemy_king_square:
                # Check if the move actually captures the king
                captured_piece = board.piece_at(move.to_square)
                if captured_piece and captured_piece.piece_type == chess.KING:
                    return move  # This is the obvious best move!

    try:
        # Make a copy so we don't modify the actual game board.
        analysis_board = board.copy(stack=False)

        # Clear the move stack and make sure the board is treated as
        # a normal position for FEN generation.
        analysis_board.clear_stack()

        # Ask Stockfish to analyse the position.
        result = engine.analyse(
            analysis_board,
            chess.engine.Limit(time=time_limit)
        )

        pv = result.get("pv")
        if not pv:
            return None

        # Return Stockfish's first move.
        return pv[0]

    except Exception as e:
        print(f"Stockfish error: {e}")
        return None

def get_stockfish_evaluation(board, engine, time_limit=0.5):
    """
    Get Stockfish's evaluation of the current position in centipawns.
    Returns an integer from White's perspective (positive = White advantage).
    Returns None if evaluation fails.
    """
    try:
        # Make a copy so we don't modify the actual game board.
        analysis_board = board.copy(stack=False)
        analysis_board.clear_stack()

        # Ask Stockfish to analyse the position.
        result = engine.analyse(
            analysis_board,
            chess.engine.Limit(time=time_limit)
        )

        score_obj = result.get("score")
        if not score_obj:
            return None

        # Check if it's a mate score
        if score_obj.is_mate():
            # For RPChess, mate is meaningless, but we can still get the value
            mate_value = score_obj.mate()
            # Convert mate to a large centipawn value
            if mate_value > 0:
                return 10000  # White mates in mate_value moves
            else:
                return -10000  # Black mates in -mate_value moves

        # Get the score as an integer (centipawns from White's perspective)
        # Try different methods to extract the score
        try:
            # Method 1: Direct .score() call
            score_int = score_obj.score()
        except AttributeError:
            try:
                # Method 2: It might be stored as a tuple (score, color)
                if isinstance(score_obj, tuple) and len(score_obj) >= 2:
                    score_int = score_obj[0]
                else:
                    # Method 3: Convert to string and parse
                    score_str = str(score_obj)
                    # Extract the numeric value from string like "PovScore(Cp(+312), WHITE)"
                    import re
                    match = re.search(r'[+-]?\d+', score_str)
                    if match:
                        score_int = int(match.group())
                    else:
                        return None
            except:
                return None

        return score_int

    except Exception as e:
        print(f"Stockfish evaluation error: {e}")
        return None


def expectimax(board, depth, turn, engine, time_limit=0.01):
    """
    Expectimax value of a position from White's perspective.
    - turn: the player to move at this decision node (chess.WHITE or chess.BLACK)
    - depth: number of decision nodes still to search
    - engine: Stockfish engine used for leaf evaluations
    - time_limit: seconds to give Stockfish per leaf (short)
    """
    # Terminal: White king missing -> Black wins, Black king missing -> White wins
    if board.king(chess.WHITE) is None:
        return -1000000
    if board.king(chess.BLACK) is None:
        return 1000000

    # Check for immediate king capture: if available, the player will take it and win.
    enemy_king_square = board.king(not turn)
    for move in board.pseudo_legal_moves:
        if move.to_square == enemy_king_square:
            # Capturing the king ends the game instantly.
            return 1000000 if turn == chess.WHITE else -1000000

    if depth == 0:
        # Use Stockfish evaluation for leaf nodes
        score = evaluate_board(board)
        if score is None:
            # Fallback to simple material evaluation if Stockfish fails
            return evaluate_board(board)
        return score

    moves = list(board.pseudo_legal_moves)
    if not moves:
        # No moves: treat as terminal with current evaluation (or draw)
        return evaluate_board(board)  # fallback

    if turn == chess.WHITE:
        # White (maximizer) wants to maximize White's advantage
        best_value = -float('inf')
        for move in moves:
            board_copy = board.copy()
            board_copy.push(move)
            # Chance node: 50% White to move, 50% Black to move
            value = 0.5 * expectimax(board_copy, depth-1, chess.WHITE, engine, time_limit) + \
                    0.5 * expectimax(board_copy, depth-1, chess.BLACK, engine, time_limit)
            if value > best_value:
                best_value = value
        return best_value
    else:  # turn == chess.BLACK
        # Black (minimizer) wants to minimize White's advantage
        best_value = float('inf')
        for move in moves:
            board_copy = board.copy()
            board_copy.push(move)
            value = 0.5 * expectimax(board_copy, depth-1, chess.WHITE, engine, time_limit) + \
                    0.5 * expectimax(board_copy, depth-1, chess.BLACK, engine, time_limit)
            if value < best_value:
                best_value = value
        return best_value

def get_expectimax_move(board, engine, depth=2, time_limit=0.01):
    """
    Return the best move for the current player using expectimax.
    - board: current board (turn indicates who moves)
    - depth: number of decision nodes to search (default 2)
    - engine: Stockfish engine used for leaf evaluations
    """
    turn = board.turn

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    # Immediate king capture: take it directly, no need to search.
    enemy_king_square = board.king(not turn)
    for move in board.pseudo_legal_moves:
        if move.to_square == enemy_king_square:
            return move

    moves = list(board.pseudo_legal_moves)
    if not moves:
        return None

    best_move = None
    if turn == chess.WHITE:
        best_value = -float('inf')
        for move in moves:
            board_copy = board.copy()
            board_copy.push(move)
            value = 0.5 * expectimax(board_copy, depth-1, chess.WHITE, engine, time_limit) + \
                    0.5 * expectimax(board_copy, depth-1, chess.BLACK, engine, time_limit)
            if value > best_value:
                best_value = value
                best_move = move
            # Optional debug print – remove if too noisy
            # print(move, value)
    else:  # Black
        best_value = float('inf')
        for move in moves:
            board_copy = board.copy()
            board_copy.push(move)
            value = 0.5 * expectimax(board_copy, depth-1, chess.WHITE, engine, time_limit) + \
                    0.5 * expectimax(board_copy, depth-1, chess.BLACK, engine, time_limit)
            if value < best_value:
                best_value = value
                best_move = move
    return best_move


def play_rpchess():
    # Initialize Stockfish engine
    if not os.path.exists(STOCKFISH_PATH):
        print(f"ERROR: Stockfish not found at {STOCKFISH_PATH}")
        print("Please update the STOCKFISH_PATH variable with the correct path to your Stockfish executable.")
        return
    
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        print("Stockfish engine loaded successfully!\n")
    except Exception as e:
        print(f"Failed to load Stockfish: {e}")
        return
    
    board = chess.Board()

    print("--- Welcome to RPChess ---")
    print("Note: No check/checkmate. To win, capture the enemy King!\n")
    
    # Print commands at game start
    print_help()

    while not board.is_game_over(claim_draw=False):
        print("\n" + "=" * 30)
        print(board)
        print("-" * 30)

        # 1. Coin toss for turn assignment
        coin = random.randint(0, 1)
        active_color = chess.WHITE if coin == 0 else chess.BLACK
        active_player = "White" if coin == 0 else "Black"
        board.turn = active_color

        print(f"Coin Toss: {coin} -> It is {active_player}'s turn!")

        # Check if active player has available moves
        available_moves = list(board.pseudo_legal_moves)
        if not available_moves:
            print(f"{active_player} has no legal moves! Skipping turn...")
            continue

        # 2. Command & Move Loop
        while True:

            # graph the board.
            if(AUTOGRAPH):
                svg_string = chess.svg.board(board=board, size=350)  # size controls the image dimensions
                with open("board_image.svg", "w") as f:
                    f.write(svg_string)

            user_input = input(f"[{active_player}] > ").strip()

            if not user_input:
                continue

            cmd_lower = user_input.lower()

            # Command: Exit the game
            if cmd_lower == "exit":
                print("Exiting game...")
                engine.quit()
                return

            # Command: Show moves for both sides
            elif cmd_lower == "moves":
                print_all_moves(board)
                continue

            # Command: Execute a Random Move
            elif cmd_lower == "random":
                chosen_move = random.choice(available_moves)
                
                # Get SAN representation before making the move
                try:
                    move_san = board.san(chosen_move)
                except (ValueError, AssertionError):
                    move_san = chosen_move.uci()
                
                print(f"[{active_player}] played random move: {move_san}")
                
                dest_square = chosen_move.to_square
                captured_piece = board.piece_at(dest_square)
                
                board.push(chosen_move)

                if captured_piece and captured_piece.piece_type == chess.KING:
                    print("\n" + "=" * 30)
                    print(board)
                    print(f"\nGAME OVER! {active_player} captured the enemy King!")
                    engine.quit()
                    return
                break

            # Command: Evaluate the position using Stockfish
            elif cmd_lower == "evaluate":
                score = get_stockfish_evaluation(board, engine)
                
                if score is None:
                    print("Failed to get evaluation.")
                else:
                    print(f"Evaluation from White's perspective: {score} centipawns")
                continue

            # Command: Execute Best Move using Stockfish
            elif cmd_lower == "best":
                # Temporarily convert pseudo-legal to legal for Stockfish
                # Stockfish needs legal moves to work properly
                if not list(board.legal_moves):
                    print("No legal moves available for Stockfish! Trying pseudo-legal...")
                    # If no legal moves, fallback to random from pseudo-legal
                    chosen_move = random.choice(available_moves)
                else:
                    # Get Stockfish's best move
                    chosen_move = get_stockfish_best_move(board, engine)
                    
                    # If Stockfish fails, fallback to random
                    if chosen_move is None:
                        print("Stockfish failed, falling back to random move...")
                        chosen_move = random.choice(available_moves)
                
                # Verify the move is in available_moves (pseudo-legal)
                if chosen_move not in available_moves:
                    print(f"Warning: Stockfish move {chosen_move} not in pseudo-legal moves!")
                    # Try to find it or fallback
                    chosen_move = random.choice(available_moves)
                
                # Get SAN representation before making the move
                try:
                    move_san = board.san(chosen_move)
                except (ValueError, AssertionError):
                    move_san = chosen_move.uci()
                
                print(f"[{active_player}] Stockfish played best move: {move_san}")
                
                dest_square = chosen_move.to_square
                captured_piece = board.piece_at(dest_square)
                
                board.push(chosen_move)

                if captured_piece and captured_piece.piece_type == chess.KING:
                    print("\n" + "=" * 30)
                    print(board)
                    print(f"\nGAME OVER! {active_player} captured the enemy King!")
                    engine.quit()
                    return
                break

            # Command: Execute Expectimax Best Move (updated to depth 2, Stockfish leaves)
            elif cmd_lower == "expectimax":
                # Pass the engine and use depth 2 with short timeout
                chosen_move = get_expectimax_move(board, engine, depth=2, time_limit=0.01)
                if chosen_move is None:
                    print("No moves available for expectimax.")
                    continue

                # Get SAN representation before making the move
                try:
                    move_san = board.san(chosen_move)
                except (ValueError, AssertionError):
                    move_san = chosen_move.uci()

                print(f"[{active_player}] Expectimax played move: {move_san}")

                dest_square = chosen_move.to_square
                captured_piece = board.piece_at(dest_square)

                board.push(chosen_move)

                if captured_piece and captured_piece.piece_type == chess.KING:
                    print("\n" + "=" * 30)
                    print(board)
                    print(f"\nGAME OVER! {active_player} captured the enemy King!")
                    engine.quit()
                    return
                break

            # command: graph the current board
            elif cmd_lower == "graph":
                # Generate the SVG string for the current board
                svg_string = chess.svg.board(board=board, size=350)  # size controls the image dimensions

                # Save the SVG to a file
                with open("board_image.svg", "w") as f:
                    f.write(svg_string)
                print("Board image saved as 'board_image.svg'. Open it in your browser.")
                continue

            # Debug Command: Switch turn manually
            elif cmd_lower == "switch":
                board.turn = not board.turn
                active_player = "White" if board.turn == chess.WHITE else "Black"
                print(f"[DEBUG] Turn manually switched to {active_player}!")
                print(board)
                available_moves = list(board.pseudo_legal_moves)
                continue

            # Command: Print Help
            elif cmd_lower == "help":
                print_help()
                continue

            # Command: Undo the last move
            elif cmd_lower == "undo":
                if len(board.move_stack) == 0:
                    print("No moves to undo!")
                else:
                    # Undo the last move
                    board.pop()
                    print("Last move undone!")
                    # Update available_moves for the current position
                    available_moves = list(board.pseudo_legal_moves)
                    # Show the current board state
                    print(board)
                continue

            # Move Processing (SAN Parsing)
            else:
                try:
                    move = board.parse_san(user_input)

                    if move in board.pseudo_legal_moves:
                        dest_square = move.to_square
                        captured_piece = board.piece_at(dest_square)
                        
                        board.push(move)

                        if captured_piece and captured_piece.piece_type == chess.KING:
                            print("\n" + "=" * 30)
                            print(board)
                            print(f"\nGAME OVER! {active_player} captured the enemy King!")
                            engine.quit()
                            return
                        break
                    else:
                        print("Illegal move for this piece. Type 'moves' to see options.")
                except ValueError:
                    print("Invalid algebraic notation (e.g., use 'e4', 'Nf3', 'Bxf7'). Type 'help' for options.")

def run_auto_games(N=10, max_moves=100):
    """
    Run N automated games between Stockfish (Black) and Expectimax (White).
    
    Each move starts with a coin toss to determine who plays.
    - White uses Expectimax
    - Black uses Stockfish
    
    Args:
        N: Number of games to play
        max_moves: Maximum moves before declaring a draw
    
    Returns:
        dict: Statistics (white_wins, black_wins, draws)
    """
    # Initialize Stockfish engine
    if not os.path.exists(STOCKFISH_PATH):
        print(f"ERROR: Stockfish not found at {STOCKFISH_PATH}")
        return None
    
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        print("Stockfish engine loaded successfully!\n")
    except Exception as e:
        print(f"Failed to load Stockfish: {e}")
        return None
    
    stats = {
        "white_wins": 0,
        "black_wins": 0,
        "draws": 0,
        "games": []
    }
    
    print(f"\n{'='*60}")
    print(f"Starting {N} games: Expectimax (White) vs Stockfish (Black)")
    print(f"Each turn determined by coin toss")
    print(f"Draw after {max_moves} moves")
    print(f"{'='*60}\n")
    
    for game_num in range(1, N + 1):
        board = chess.Board()
        move_count = 0
        game_over = False
        game_moves = []
        coin_tosses = []  # Track coin toss results
        
        print(f"\n--- Game {game_num}/{N} ---")
        
        while not game_over and move_count < max_moves:
            # Coin toss for turn assignment
            coin = random.randint(0, 1)
            active_color = chess.WHITE if coin == 0 else chess.BLACK
            active_player = "White (Expectimax)" if coin == 0 else "Black (Stockfish)"
            board.turn = active_color
            
            coin_tosses.append(coin)
            print(f"Coin Toss: {coin} -> {active_player} to play")
            
            # Check if active player has available moves
            available_moves = list(board.pseudo_legal_moves)
            if not available_moves:
                print(f"{active_player} has no moves! Skipping...")
                continue
            
            # Check for immediate king capture
            enemy_king = board.king(not active_color)
            king_captured = False
            if enemy_king:
                for move in board.pseudo_legal_moves:
                    if move.to_square == enemy_king:
                        captured = board.piece_at(move.to_square)
                        if captured and captured.piece_type == chess.KING:
                            board.push(move)
                            game_moves.append(move.uci())
                            print(f"{active_player} captures the king!")
                            game_over = True
                            if active_color == chess.WHITE:
                                stats["white_wins"] += 1
                            else:
                                stats["black_wins"] += 1
                            king_captured = True
                            break
                if king_captured:
                    break
            
            # White uses Expectimax
            if active_color == chess.WHITE:
                chosen_move = get_expectimax_move(board, engine, depth=3, time_limit=0.1)
                if chosen_move is None:
                    print("Expectimax failed, using random move")
                    chosen_move = random.choice(list(board.pseudo_legal_moves))
                
                # Verify move
                if chosen_move not in list(board.pseudo_legal_moves):
                    print("errr")
                    chosen_move = random.choice(list(board.pseudo_legal_moves))
                
                move_san = board.san(chosen_move)
                print(f"White (Expectimax) plays: {move_san}")
            
            # Black uses Stockfish
            else:
                if not list(board.legal_moves):
                    print("No legal moves for Stockfish, using random move")
                    chosen_move = random.choice(list(board.pseudo_legal_moves))
                else:
                    chosen_move = get_stockfish_best_move(board, engine, time_limit=4)
                    if chosen_move is None:
                        print("Stockfish failed, using random move")
                        chosen_move = random.choice(list(board.pseudo_legal_moves))
                
                # Verify move
                if chosen_move not in list(board.pseudo_legal_moves):
                    print("errr")
                    chosen_move = random.choice(list(board.pseudo_legal_moves))
                
                move_san = board.san(chosen_move)
                print(f"Black (Stockfish) plays: {move_san}")
            
            # Make the move
            dest_square = chosen_move.to_square
            captured_piece = board.piece_at(dest_square)
            board.push(chosen_move)
            game_moves.append(chosen_move.uci())
            
            # Check for king capture after the move (should already be caught above, but just in case)
            if captured_piece and captured_piece.piece_type == chess.KING:
                print(f"{active_player} captures the king!")
                game_over = True
                if active_color == chess.WHITE:
                    stats["white_wins"] += 1
                else:
                    stats["black_wins"] += 1
                break
            
            move_count += 1
        
        # Check if game ended by draw (max moves reached)
        if not game_over and move_count >= max_moves:
            print(f"\nGame {game_num} ended in a draw (max moves reached)")
            stats["draws"] += 1
        
        # Determine result
        if game_over:
            if stats["white_wins"] > stats["black_wins"]:
                result = "White (Expectimax)"
            elif stats["black_wins"] > stats["white_wins"]:
                result = "Black (Stockfish)"
            else:
                result = "Unknown"
        else:
            result = "Draw"
        
        stats["games"].append({
            "result": result,
            "moves": game_moves,
            "move_count": move_count,
            "coin_tosses": coin_tosses
        })
        
        # Print result
        print(f"\nGame {game_num} cumulative result: {result}")
        print(f"Total moves: {move_count}")
        print("-" * 30)
    
    # Report statistics
    engine.quit()
    
    print(f"\n{'='*60}")
    print("FINAL STATISTICS")
    print(f"{'='*60}")
    print(f"Total games: {N}")
    print(f"White (Expectimax) wins: {stats['white_wins']} ({stats['white_wins']/N*100:.1f}%)")
    print(f"Black (Stockfish) wins: {stats['black_wins']} ({stats['black_wins']/N*100:.1f}%)")
    print(f"Draws: {stats['draws']} ({stats['draws']/N*100:.1f}%)")
    print(f"{'='*60}\n")
    
    return stats

if __name__ == "__main__":
    # play_rpchess()
    run_auto_games(N=10, max_moves=100)