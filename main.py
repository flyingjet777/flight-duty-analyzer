from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List
import os
from datetime import datetime

from pdf_parser import parse_schedule_pdf
from limits_engine import calculate_flight_metrics, evaluate_cumulative_limits

app = FastAPI(title="Flight Duty Analyzer API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend is running successfully."}

@app.post("/api/analyze")
async def analyze_schedules(files: List[UploadFile] = File(...)):
    all_flights = []
    
    for file in files:
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        try:
            flights = parse_schedule_pdf(temp_path)
            all_flights.extend(flights)
        except Exception as e:
            print(f"Error parsing {file.filename}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    if not all_flights:
        return {"error": "No valid flights found in PDFs."}
        
    processed = calculate_flight_metrics(all_flights)
    
    # Sort chronologically
    # max datetime if None
    processed.sort(key=lambda x: x['std'] if x['std'] else datetime.max.replace(tzinfo=x['std'].tzinfo if hasattr(x['std'], 'tzinfo') else None))
    
    # Fallback simpler sort if timezone offsets conflict:
    # Actually KST aware datetime sorts fine
    
    processed = evaluate_cumulative_limits(processed)
    
    return {"status": "success", "flights": processed}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
