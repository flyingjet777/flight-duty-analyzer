from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import airport_db

import pytz
KST = pytz.timezone('Asia/Seoul')

def parse_flight_datetime(year, month, time_dict):
    if not time_dict:
        return None
    try:
        dt = datetime(year, month, time_dict['day'], time_dict['hour'], time_dict['minute'])
        return dt
    except ValueError:
        return None

def format_minutes(total_minutes: float) -> str:
    """Format total minutes into 'HH+MM'."""
    hours = int(total_minutes // 60)
    mins = int(total_minutes % 60)
    return f"{hours:02d}+{mins:02d}"

def calculate_flight_metrics(parsed_flights):
    raw_processed = []
    
    for i, flight in enumerate(parsed_flights):
        year = flight['year']
        month = flight['month']
        
        std_naive = parse_flight_datetime(year, month, flight['std_raw'])
        sta_naive = parse_flight_datetime(year, month, flight['sta_raw'])
        show_up_naive = parse_flight_datetime(year, month, flight['show_up_raw'])
        
        if std_naive and sta_naive:
            if sta_naive.day < std_naive.day:
                sta_naive = sta_naive + relativedelta(months=1)
        
        # If no show up is provided, we default it to STD - 90 mins for parsing
        if not show_up_naive and std_naive:
            show_up_naive = std_naive - timedelta(minutes=90)
            
        if show_up_naive and std_naive:
            if show_up_naive.day > std_naive.day:
                show_up_naive = show_up_naive - relativedelta(months=1)
                
        std_kst = airport_db.convert_to_kst(std_naive, flight['dep_airport']) if std_naive else None
        sta_kst = airport_db.convert_to_kst(sta_naive, flight['arr_airport']) if sta_naive else None
        show_up_kst = airport_db.convert_to_kst(show_up_naive, flight['dep_airport']) if show_up_naive else None
        
        flight_time_delta = (sta_kst - std_kst) if (sta_kst and std_kst) else timedelta(0)
        fdp_delta = (sta_kst - show_up_kst) if (sta_kst and show_up_kst) else timedelta(0)
        
        flight_time_mins = flight_time_delta.total_seconds() / 60.0
        fdp_mins = fdp_delta.total_seconds() / 60.0

        is_home_base = flight['arr_airport'] in ['ICN', 'GMP', 'PUS', 'CJU']
        
        if is_home_base:
            rest_start = sta_kst + timedelta(minutes=30) if sta_kst else None
        else:
            rest_start = sta_kst + timedelta(hours=2) if sta_kst else None
            
        flight_data = {
            "flight_no": flight["flight_no"],
            "dep_airport": flight["dep_airport"],
            "arr_airport": flight["arr_airport"],
            "sector": f"{flight['dep_airport']}/{flight['arr_airport']}",
            "std": std_kst,
            "sta": sta_kst,
            "show_up": show_up_kst,
            "dep_date_str_local": std_naive.strftime("%y/%m/%d") if std_naive else "-",
            "std_local_str": std_naive.strftime("%m/%d %H:%M") if std_naive else "-",
            "sta_local_str": sta_naive.strftime("%m/%d %H:%M") if sta_naive else "-",
            "flight_time_mins": flight_time_mins,
            "fdp_mins": fdp_mins,
            "rest_start": rest_start,
            "is_home_base": is_home_base,
            "rest_period_mins": 0.0,
            "rest_period_str": "",
            "rest_emoji": ""
        }
        raw_processed.append(flight_data)
        
    # ------------- MERGE DUTY PERIODS (Short Hauls <= 13h) -------------
    # Sort chronologically first just in case
    raw_processed.sort(key=lambda x: x['std'] if x['std'] else datetime.max.replace(tzinfo=KST))
    
    merged_processed = []
    current_duty = []
    
    for f in raw_processed:
        if not f['std'] or not f['sta']:
            merged_processed.append(f)
            continue
            
        if not current_duty:
            current_duty = [f]
            continue
            
        first_f = current_duty[0]
        last_f = current_duty[-1]
        
        ground_time_mins = (f['std'] - last_f['sta']).total_seconds() / 60.0
        
        # Calculate what the new FDP would be
        # Use first flight's show up, up to the current flight's STA
        potential_fdp_mins = (f['sta'] - first_f['show_up']).total_seconds() / 60.0 if first_f['show_up'] else 0
        
        # If ground time is less than standard rest (< 10h), they are consecutive flights
        # And if total FDP <= 13h, we merge them into one line.
        if ground_time_mins < (10 * 60) and potential_fdp_mins <= (13 * 60):
            current_duty.append(f)
        else:
            # End of duty period, package current_duty into merged_processed
            merged_processed.append(package_duty(current_duty))
            current_duty = [f]
            
    if current_duty:
        merged_processed.append(package_duty(current_duty))

    # ------------- STAGE 2: Rest Periods -------------
    for i in range(len(merged_processed) - 1):
        curr_flight = merged_processed[i]
        next_flight = merged_processed[i+1]
        
        if curr_flight['rest_start'] and next_flight['std']:
            if curr_flight['is_home_base']:
                rest_end = next_flight['show_up']
            else:
                rest_end = next_flight['std'] - timedelta(hours=2)
                
            rest_delta = rest_end - curr_flight['rest_start']
            rest_mins = rest_delta.total_seconds() / 60.0
            rest_hours = rest_mins / 60.0
            
            curr_flight['rest_period_mins'] = rest_mins
            curr_flight['rest_period_str'] = format_minutes(rest_mins)
            
            if rest_hours >= 48:
                curr_flight['rest_emoji'] = "💜"
            elif 36 <= rest_hours < 48:
                curr_flight['rest_emoji'] = "🟢"
            elif 24 <= rest_hours < 36:
                curr_flight['rest_emoji'] = "🟡"
            elif rest_hours > 0:
                curr_flight['rest_emoji'] = "🔴"

    return merged_processed

def package_duty(duty_list):
    """Combine a list of consecutive flight dicts into a single flight dict representations."""
    if len(duty_list) == 1:
        # Just format strings for the single flight
        f = duty_list[0]
        f['flight_time_str'] = format_minutes(f['flight_time_mins'])
        f['fdp_str'] = format_minutes(f['fdp_mins'])
        return f
        
    first_f = duty_list[0]
    last_f = duty_list[-1]
    
    sectors = [first_f['dep_airport']]
    for d in duty_list:
        sectors.append(d['arr_airport'])
    combined_sector = "/".join(sectors)
    
    combined_flight_no = "/".join([d['flight_no'] for d in duty_list])
    
    total_flight_mins = sum([d['flight_time_mins'] for d in duty_list])
    total_fdp_mins = (last_f['sta'] - first_f['show_up']).total_seconds() / 60.0 if first_f['show_up'] else 0
    
    return {
        "flight_no": combined_flight_no,
        "sector": combined_sector,
        "std": first_f['std'],
        "sta": last_f['sta'],
        "show_up": first_f['show_up'],
        "dep_date_str_local": first_f.get('dep_date_str_local', '-'),
        "std_local_str": first_f.get('std_local_str', '-'),
        "sta_local_str": last_f.get('sta_local_str', '-'),
        "flight_time_mins": total_flight_mins,
        "flight_time_str": format_minutes(total_flight_mins),
        "fdp_mins": total_fdp_mins,
        "fdp_str": format_minutes(total_fdp_mins),
        "rest_start": last_f['rest_start'],
        "is_home_base": last_f['is_home_base'],
        "rest_period_mins": 0.0,
        "rest_period_str": "",
        "rest_emoji": "",
        "dep_airport": first_f['dep_airport'],
        "arr_airport": last_f['arr_airport']
    }

def evaluate_cumulative_limits(processed_flights):
    for i, flight in enumerate(processed_flights):
        warnings = []
        current_time = flight['std']
        if not current_time: continue
        
        # Duty time = FDP + 30m
        duty_period_mins = flight['fdp_mins'] + 30
        flight['duty_period_mins'] = duty_period_mins
        
        seven_days_ago = current_time - timedelta(days=7)
        duty_last_7_mins = sum([f.get('duty_period_mins', 0) for f in processed_flights[:i+1] if f['std'] and f['std'] >= seven_days_ago])
        
        # 60 hours = 3600 mins
        if duty_last_7_mins > (60 * 60):
            warnings.append(f"7일 누적 근무 초과: {format_minutes(duty_last_7_mins)} / 60시간")
            
        twentyeight_days_ago = current_time - timedelta(days=28)
        duty_last_28_mins = sum([f.get('duty_period_mins', 0) for f in processed_flights[:i+1] if f['std'] and f['std'] >= twentyeight_days_ago])
        flight_last_28_mins = sum([f.get('flight_time_mins', 0) for f in processed_flights[:i+1] if f['std'] and f['std'] >= twentyeight_days_ago])
        
        # 190 hours = 11400 mins
        if duty_last_28_mins > (190 * 60):
            warnings.append(f"28일 누적 근무 초과: {format_minutes(duty_last_28_mins)} / 190시간")
            
        # 100 hours = 6000 mins
        if flight_last_28_mins > (100 * 60):
            warnings.append(f"28일 비행시간 경고: {format_minutes(flight_last_28_mins)} / 100시간(2P) 기준 넘음")
            
        this_year_start = current_time - relativedelta(years=1)
        flight_last_365_mins = sum([f.get('flight_time_mins', 0) for f in processed_flights[:i+1] if f['std'] and f['std'] > this_year_start])
        
        if flight_last_365_mins >= (950 * 60):
            warnings.append(f"1년 비행시간 1000시간 근접: 현재 {format_minutes(flight_last_365_mins)}")
            
        flight['cumulative_duty_7d_str'] = format_minutes(duty_last_7_mins)
        flight['cumulative_duty_28d_str'] = format_minutes(duty_last_28_mins)
        flight['cumulative_flight_28d_str'] = format_minutes(flight_last_28_mins)
        flight['cumulative_flight_365d_str'] = format_minutes(flight_last_365_mins)
        
        flight['cumulative_duty_7d_mins'] = duty_last_7_mins
        flight['cumulative_duty_28d_mins'] = duty_last_28_mins
        flight['cumulative_flight_28d_mins'] = flight_last_28_mins
        flight['warnings'] = warnings
        
    return processed_flights

if __name__ == "__main__":
    from pdf_parser import parse_schedule_pdf
    flights = parse_schedule_pdf("202601.pdf")
    processed = calculate_flight_metrics(flights)
    processed = evaluate_cumulative_limits(processed)    
    for p in processed[:4]:
        print(f"[{p['std'].strftime('%Y-%m-%d')}] FLT {p['flight_no']} {p['sector']} | FDP: {p['fdp_str']} | Flight Time: {p['flight_time_str']}")
        if p['rest_period_mins'] > 0:
            print(f"   -> Rest: {p['rest_period_str']} {p['rest_emoji']}")
        if p.get('warnings'):
            print(f"   -> WARNINGS: {', '.join(p['warnings'])}")
