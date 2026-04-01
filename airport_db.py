import airportsdata
from datetime import datetime
import pytz

# Load airports data indexed by IATA code
try:
    airports = airportsdata.load('IATA')
except Exception as e:
    print(f"Error loading airports data: {e}")
    airports = {}

def get_airport_info(iata_code: str):
    """Get the timezone name and details for an IATA airport code."""
    iata_code = iata_code.upper()
    if iata_code not in airports:
        return None
    
    airport = airports[iata_code]
    return {
        "iata": iata_code,
        "name": airport.get('name', ''),
        "city": airport.get('city', ''),
        "country": airport.get('country', ''),
        "tz": airport.get('tz', 'UTC'), # e.g. 'America/Los_Angeles'
    }

def convert_to_kst(local_time: datetime, iata_code: str) -> datetime:
    """
    Convert a naive local datetime at a given airport to a KST timezone-aware datetime.
    """
    info = get_airport_info(iata_code)
    # Default to UTC if airport not found, but log a warning ideally
    tz_name = info['tz'] if info and 'tz' in info else 'UTC'
    
    local_tz = pytz.timezone(tz_name)
    kst_tz = pytz.timezone('Asia/Seoul')
    
    # Localize the naive datetime to the airport's timezone
    if local_time.tzinfo is None:
        aware_local = local_tz.localize(local_time)
    else:
        aware_local = local_time.astimezone(local_tz)

    # Convert to KST
    aware_kst = aware_local.astimezone(kst_tz)
    return aware_kst

def get_time_diff_hours(iata_code1: str, iata_code2: str) -> float:
    """
    Calculate the static timezone difference in hours between two airports.
    This uses current time to account for DST changes.
    """
    info1 = get_airport_info(iata_code1)
    info2 = get_airport_info(iata_code2)
    
    tz1_name = info1['tz'] if info1 else 'UTC'
    tz2_name = info2['tz'] if info2 else 'UTC'
    
    tz1 = pytz.timezone(tz1_name)
    tz2 = pytz.timezone(tz2_name)
    
    now = datetime.utcnow()
    offset1 = tz1.utcoffset(now).total_seconds() / 3600.0
    offset2 = tz2.utcoffset(now).total_seconds() / 3600.0
    
    return abs(offset1 - offset2)
