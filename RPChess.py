import chess
import random

def print_help():
    print("==================================================")
    print("               SPECIAL COMMANDS MENU              ")
    print("==================================================")
    print("  moves      : Print all pseudo-legal moves for both White and Black (SAN)")
    print("  random     : Play a random pseudo-legal move for the current player")
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

def play_rpchess():
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
                            return
                        break
                    else:
                        print("Illegal move for this piece. Type 'moves' to see options.")
                except ValueError:
                    print("Invalid algebraic notation (e.g., use 'e4', 'Nf3', 'Bxf7'). Type 'help' for options.")

if __name__ == "__main__":
    play_rpchess()