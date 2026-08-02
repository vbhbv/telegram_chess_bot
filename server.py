import os
import json
import asyncio
import chess
import chess.engine
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from database import init_db_pool, get_db_pool, close_db_pool

load_dotenv()

app = FastAPI(title="Telegram Chess Engine & Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, game_id: str, websocket: WebSocket):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = []
        self.active_connections[game_id].append(websocket)

    def disconnect(self, game_id: str, websocket: WebSocket):
        if game_id in self.active_connections:
            if websocket in self.active_connections[game_id]:
                self.active_connections[game_id].remove(websocket)
            if not self.active_connections[game_id]:
                del self.active_connections[game_id]

    async def broadcast(self, game_id: str, message: dict):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id]:
                await connection.send_json(message)

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    await init_db_pool()

@app.on_event("shutdown")
async def shutdown_event():
    await close_db_pool()

@app.get("/")
async def get_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Telegram Chess Server Running</h1>")

async def get_ai_move(board_fen: str, difficulty: int = 1) -> str:
    try:
        transport, engine = await chess.engine.popen_uci(STOCKFISH_PATH)
        board = chess.Board(board_fen)
        limit = chess.engine.Limit(time=0.5, depth=difficulty * 3)
        result = await engine.play(board, limit)
        await engine.quit()
        return result.move.uci() if result.move else None
    except Exception as e:
        print(f"Stockfish Error: {e}")
        return None

@app.websocket("/ws/{game_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, user_id: int):
    await manager.connect(game_id, websocket)
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            game = await conn.fetchrow("SELECT * FROM games WHERE game_id = $1", game_id)
            if not game:
                await websocket.send_json({"type": "error", "message": "المباراة غير موجودة"})
                return
            
            await websocket.send_json({
                "type": "init",
                "fen": game["fen"],
                "status": game["status"],
                "game_mode": game["game_mode"]
            })

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("action")

            if action == "move":
                move_uci = payload.get("move")
                async with pool.acquire() as conn:
                    game = await conn.fetchrow("SELECT * FROM games WHERE game_id = $1", game_id)
                    board = chess.Board(game["fen"])
                    move = chess.Move.from_uci(move_uci)
                    
                    if move in board.legal_moves:
                        board.push(move)
                        new_fen = board.fen()
                        new_status = "active"
                        
                        if board.is_checkmate():
                            new_status = "checkmate"
                        elif board.is_stalemate() or board.is_insufficient_material():
                            new_status = "draw"

                        await conn.execute(
                            "UPDATE games SET fen = $1, status = $2, moves = moves || $3 || ' ', updated_at = CURRENT_TIMESTAMP WHERE game_id = $4",
                            new_fen, new_status, move_uci, game_id
                        )

                        await manager.broadcast(game_id, {
                            "type": "move",
                            "move": move_uci,
                            "fen": new_fen,
                            "status": new_status,
                            "turn": "white" if board.turn == chess.WHITE else "black"
                        })

                        # لعب الذكاء الاصطناعي (ضد الكمبيوتر)
                        if game["game_mode"] == "ai" and new_status == "active" and not board.is_game_over():
                            ai_move = await get_ai_move(new_fen, game["difficulty"])
                            if ai_move:
                                board.push(chess.Move.from_uci(ai_move))
                                ai_fen = board.fen()
                                ai_status = "checkmate" if board.is_checkmate() else ("draw" if board.is_stalemate() else "active")
                                
                                await conn.execute(
                                    "UPDATE games SET fen = $1, status = $2, moves = moves || $3 || ' ', updated_at = CURRENT_TIMESTAMP WHERE game_id = $4",
                                    ai_fen, ai_status, ai_move, game_id
                                )

                                await manager.broadcast(game_id, {
                                    "type": "move",
                                    "move": ai_move,
                                    "fen": ai_fen,
                                    "status": ai_status,
                                    "turn": "white" if board.turn == chess.WHITE else "black"
                                })

    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)
    except Exception as e:
        print(f"WebSocket Error: {e}")
        manager.disconnect(game_id, websocket)
  
