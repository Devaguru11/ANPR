from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.model_service import ModelService
from config.config import settings

app = FastAPI(title="Assistant Enhance Service")
model_service = ModelService()

@app.on_event("startup")
async def startup_event():
    # Load model on startup
    model_service.load_model(settings.model_name)

class ChatRequest(BaseModel):
    session_id: str
    message: str

class DebugRequest(BaseModel):
    session_id: str

@app.get("/assistant_enhance/health")
def health_check():
    return {"status": "ok", "environment": settings.environment}

@app.post("/assistant_enhance/chat")
def chat(request: ChatRequest):
    try:
        result = model_service.predict(request.message)
        # Format the model prediction nicely for the chat interface
        reply_message = f"I analyzed your text and predicted: {result[0]['label']} with a confidence of {result[0]['score']:.2f}."
        return {"session_id": request.session_id, "message": reply_message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assistant_enhance/debug")
def debug(request: DebugRequest):
    return {"session_id": request.session_id, "debug_info": "Service is running normally."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
