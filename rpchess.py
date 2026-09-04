import chess
import chess.engine
import random
import os

# Global engine variable (initialized once)
STOCKFISH_PATH = "./stockfish/stockfish-windows-x86-64-avx2.exe"  # Change this to your actual path

def print_help():
    print("==================================================")
    print("               SPECIAL COMMANDS MENU              ")
    print("==================================================")
    print("  moves      : Print all pseudo-legal moves for both White and Black (SAN)")
    print("  random     : Play a random pseudo-legal move for the current player")
    print("  best       : Play the best move (uses Stockfish engine)")
    print("  switch     : [Debug] Manually flip the turn to the other player")
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

    Uses the already-running SimpleEngine instance.
    """

    try:
        # Make a copy so we don't modify the actual game board.
        analysis_board = board.copy(stack=False)

        # python-chess considers positions with kings in check etc.
        # invalid for normal chess. For our RPChess variant we don't care.
        #
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
            user_input = input(f"[{active_player}] > ").strip()

            if not user_input:
                continue

            cmd_lower = user_input.lower()

            # Command: Show moves for both sides
            if cmd_lower == "moves":
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

if __name__ == "__main__":
    play_rpchess()