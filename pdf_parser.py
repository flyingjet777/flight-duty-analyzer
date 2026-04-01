import pdfplumber
import re
from datetime import datetime
import pandas as pd

def parse_schedule_pdf(file_path: str):
    """
    Parse an Asiana Airlines schedule PDF and extract flight events.
    """
    flights = []
    current_year = None
    current_month = None

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            # First, extract text to find the YEAR/MONTH header
            text = page.extract_text()
            if not text: continue
            
            # Look for "MONTH: YYYYMM"
            month_match = re.search(r'MONTH:\s*(\d{4})(\d{2})', text)
            if month_match:
                current_year = int(month_match.group(1))
                current_month = int(month_match.group(2))
            
            # Extract tables
            tables = page.extract_tables()
            if not tables: continue
            
            # Usually the schedule is in the first table
            table = tables[0]
            if len(table) < 2: continue
            
            # Validate headers optionally
            headers = [h.replace('\\n', ' ') if h else '' for h in table[0]]
            
            # Process rows
            for row in table[1:]:
                # If row is shorter than expected, pad it (sometimes pdfplumber returns unequal rows)
                if len(row) < 6: continue
                
                date_str = row[0]
                flight_no = row[1]
                show_up = row[2]
                sector = row[3]
                std = row[4]
                sta = row[5]
                
                # Check if it's an actual flight (not DAYOFF, etc.)
                if not flight_no or not sector or '/' not in sector:
                    continue
                
                dep_airport, arr_airport = sector.split('/')
                
                # Helper to convert "DDHH:MM" to naive datetime
                def parse_time(time_str):
                    if not time_str or len(time_str.replace(':', '')) < 6: return None
                    time_str = time_str.replace(':', '') # "0920:00" -> "092000" or similar?
                    # The format looks like: "0920:00" -> "DDHH:MM"
                    # Wait, look at the example: "0918:40" -> Day 09, 18:40
                    day = int(time_str[0:2])
                    hour = int(time_str[2:4])
                    minute = int(time_str[5:7]) if ':' in time_str else int(time_str[4:6])
                    
                    # Handle month rollover implicitly if day < 5 but current month is around 30/31
                    # A more robust way: use the year/month
                    # Note: flight end might be the next month, let's keep it simple for now and handle rollover
                    # if day is 01 and we started parsing on 31, we need to add a month.
                    return {
                        "day": day, "hour": hour, "minute": minute
                    }
                
                show_up_parsed = parse_time(show_up) if show_up else None
                std_parsed = parse_time(std)
                sta_parsed = parse_time(sta)
                
                if std_parsed and sta_parsed:
                    # Construct datetimes
                    # We will handle day transitions (e.g. month rollover) later in the limits_engine
                    flights.append({
                        "year": current_year,
                        "month": current_month,
                        "flight_no": flight_no,
                        "dep_airport": dep_airport,
                        "arr_airport": arr_airport,
                        "show_up_raw": show_up_parsed,
                        "std_raw": std_parsed,
                        "sta_raw": sta_parsed
                    })

    return flights

# Simple test if run directly
if __name__ == "__main__":
    flights = parse_schedule_pdf("202601.pdf")
    for f in flights[:3]:
        print(f)
