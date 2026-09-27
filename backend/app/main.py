
from fastapi import FastAPI
from supabase_client import supabase
app = FastAPI(
    title="Dataset Provenance API",
    version="1.0.0"
)

@app.get('/')
def root():
    return {
        "message": "Dataset Provenance API is running"
    }

@app.get("/test-supabase")
def test_supabase():
    response = supabase.table("users").select("*").execute()

    return {
        "data": response.data
    }