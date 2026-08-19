from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import planner, generator, extractor, grader, bank, ingestion, textbooks

app = FastAPI(title="MathFlow AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(planner.router)
app.include_router(generator.router)
app.include_router(extractor.router)
app.include_router(grader.router)
app.include_router(bank.router)
app.include_router(ingestion.router)
app.include_router(textbooks.router)


@app.get("/ping")
async def ping():
    return {"status": "ok"}
