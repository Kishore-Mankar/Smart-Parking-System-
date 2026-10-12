"""
new_features.py  –  Enhanced Smart Parking System
Major Project Additions:
  1. Vehicle Number Plate Recognition (simulated)
  2. Dynamic Pricing Engine
  3. Loyalty / Reward Points System
  4. Slot Recommendation Engine
  5. Carbon Footprint Tracker
  6. Peak Hour Surge Pricing Alerts
  7. Group Booking (reserve multiple slots)
  8. Smart Waitlist System
  9. EV Charging Slot Management
 10. Parking History Analytics (per-user heatmap)
"""

import random
import string
from datetime import datetime, timedelta
import math


# ─────────────────────────────────────────────────────────────────────────────
# 1. Vehicle Number Plate Recognition (Simulation)
# ─────────────────────────────────────────────────────────────────────────────

INDIAN_STATES = ['AP', 'TS', 'KA', 'MH', 'TN', 'DL', 'UP', 'GJ', 'RJ', 'MP']

def generate_fake_plate() -> str:
    state = random.choice(INDIAN_STATES)
    dist  = str(random.randint(10, 99))
    alpha = ''.join(random.choices(string.ascii_uppercase, k=2))
    num   = str(random.randint(1000, 9999))
    return f"{state} {dist} {alpha} {num}"

def recognize_plate(image_data_hint: str = None) -> dict:
    """
    Simulate OCR-based number plate recognition.
    In production: integrate OpenCV + EasyOCR or Google Vision API.
    """
    plate = generate_fake_plate()
    confidence = round(random.uniform(88.5, 99.2), 1)
    return {
        'plate_number': plate,
        'confidence':   confidence,
        'recognized':   True,
        'timestamp':    datetime.now().isoformat(),
        'note':         'Production: Replace with OpenCV + EasyOCR pipeline',
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dynamic Pricing Engine
# ─────────────────────────────────────────────────────────────────────────────

class DynamicPricingEngine:
    """
    Surge pricing based on occupancy, time-of-day, and day-of-week.
    Multiplier range: 0.8× (off-peak) to 2.5× (peak + near-full).
    """

    PEAK_HOURS  = list(range(8, 10)) + list(range(17, 20))  # 8-9, 17-19
    NIGHT_HOURS = list(range(0, 6)) + list(range(22, 24))

    def calculate_price(self, base_rate: float, occupancy_pct: float,
                        hour: int, day_of_week: int) -> dict:
        multiplier = 1.0

        # Occupancy surge
        if occupancy_pct >= 90:   multiplier *= 2.0
        elif occupancy_pct >= 75: multiplier *= 1.5
        elif occupancy_pct >= 50: multiplier *= 1.2
        elif occupancy_pct < 25:  multiplier *= 0.85

        # Time-of-day
        if hour in self.PEAK_HOURS:   multiplier *= 1.3
        elif hour in self.NIGHT_HOURS: multiplier *= 0.8

        # Weekend bump
        if day_of_week >= 5: multiplier *= 1.15

        multiplier  = round(min(2.5, max(0.8, multiplier)), 2)
        final_price = round(base_rate * multiplier, 2)

        if multiplier > 1.4:  label, color = 'Surge Pricing',  '#ef4444'
        elif multiplier > 1.0: label, color = 'Standard',       '#f59e0b'
        else:                   label, color = 'Off-Peak Deal',  '#22c55e'

        return {
            'base_rate':   base_rate,
            'multiplier':  multiplier,
            'final_price': final_price,
            'label':       label,
            'color':       color,
            'savings':     round((base_rate - final_price), 2) if multiplier < 1 else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Loyalty / Reward Points System
# ─────────────────────────────────────────────────────────────────────────────

POINTS_PER_RUPEE  = 1       # 1 point per ₹1 spent
TIER_THRESHOLDS   = {'Bronze': 0, 'Silver': 500, 'Gold': 2000, 'Platinum': 5000}
TIER_MULTIPLIERS  = {'Bronze': 1.0, 'Silver': 1.25, 'Gold': 1.5, 'Platinum': 2.0}
TIER_COLORS       = {'Bronze': '#cd7f32', 'Silver': '#a8a9ad', 'Gold': '#ffd700', 'Platinum': '#e5e4e2'}

def calculate_points_earned(amount: float, tier: str = 'Bronze') -> int:
    multiplier = TIER_MULTIPLIERS.get(tier, 1.0)
    return int(amount * POINTS_PER_RUPEE * multiplier)

def get_tier(total_points: int) -> str:
    tier = 'Bronze'
    for name, threshold in TIER_THRESHOLDS.items():
        if total_points >= threshold:
            tier = name
    return tier

def points_to_rupees(points: int) -> float:
    return round(points * 0.10, 2)  # 10 paise per point

def get_loyalty_status(total_points: int) -> dict:
    tier = get_tier(total_points)
    tiers_list = list(TIER_THRESHOLDS.keys())
    idx = tiers_list.index(tier)
    next_tier = tiers_list[idx + 1] if idx < len(tiers_list) - 1 else None
    next_threshold = TIER_THRESHOLDS.get(next_tier, total_points)
    progress = min(100, int((total_points - TIER_THRESHOLDS[tier]) /
                             max(1, next_threshold - TIER_THRESHOLDS[tier]) * 100))
    return {
        'tier':            tier,
        'total_points':    total_points,
        'rupee_value':     points_to_rupees(total_points),
        'tier_color':      TIER_COLORS[tier],
        'next_tier':       next_tier,
        'points_to_next':  max(0, next_threshold - total_points),
        'progress_pct':    progress,
        'multiplier':      TIER_MULTIPLIERS[tier],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Slot Recommendation Engine
# ─────────────────────────────────────────────────────────────────────────────

class SlotRecommender:
    """
    Recommends the best parking slot based on:
    - Proximity to entrance (A-row = closest)
    - User preferences (EV charging, disabled-friendly, covered)
    - Slot type availability
    """

    ROW_PROXIMITY = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1, 'F': 1}

    def score_slot(self, slot_code: str, preferences: dict) -> float:
        if not slot_code:
            return 0
        row = slot_code[0].upper()
        proximity = self.ROW_PROXIMITY.get(row, 1)
        score = proximity * 10

        # Prefer lower slot numbers (closer to stairs/lift)
        try:
            num = int(slot_code[1:])
            score += max(0, 6 - num)
        except ValueError:
            pass

        # Preference bonuses
        if preferences.get('ev_charging') and row in ('A', 'B'):
            score += 20
        if preferences.get('covered') and row in ('A', 'B', 'C'):
            score += 15
        if preferences.get('disabled') and 'A1' in slot_code:
            score += 50

        return score

    def recommend(self, available_slots: list, preferences: dict = None) -> list:
        preferences = preferences or {}
        scored = [(s, self.score_slot(s['slot_code'], preferences))
                  for s in available_slots]
        scored.sort(key=lambda x: -x[1])
        top3 = scored[:3]
        return [{'slot': s, 'score': sc, 'reason': self._reason(s['slot_code'], preferences)}
                for s, sc in top3]

    def _reason(self, code: str, prefs: dict) -> str:
        row = code[0].upper() if code else '?'
        if prefs.get('ev_charging') and row in ('A', 'B'):
            return '⚡ EV Charging Available'
        if prefs.get('disabled') and 'A1' in code:
            return '♿ Disabled-Friendly Spot'
        if row == 'A':
            return '🚪 Closest to Entrance'
        if row == 'B':
            return '📍 Near Entrance'
        return '🅿️ Good Availability'


# ─────────────────────────────────────────────────────────────────────────────
# 5. Carbon Footprint Tracker
# ─────────────────────────────────────────────────────────────────────────────

# kg CO2 saved per hour of parking vs. circling (avg car emits ~120g CO2/km,
# circling ~2 km/15 min → ~0.96 kg/hr saved by going straight to a spot)
CO2_SAVED_PER_HOUR = 0.96   # kg CO2
TREES_PER_KG_CO2   = 0.1    # one tree absorbs ~10 kg CO2/year → 0.1 per kg shorthand

def calculate_carbon_savings(total_bookings: int, avg_duration_hours: float = 2.0) -> dict:
    total_hours = total_bookings * avg_duration_hours
    co2_saved   = round(total_hours * CO2_SAVED_PER_HOUR, 2)
    trees_equiv = round(co2_saved * TREES_PER_KG_CO2, 2)
    km_saved    = round(total_hours * 2, 1)  # 2 km circling saved per hour
    return {
        'total_bookings':       total_bookings,
        'total_hours_parked':   round(total_hours, 1),
        'co2_saved_kg':         co2_saved,
        'trees_equivalent':     trees_equiv,
        'km_not_circled':       km_saved,
        'fuel_saved_litres':    round(km_saved / 15, 2),  # avg 15 km/litre
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Peak-Hour Surge Pricing Alert
# ─────────────────────────────────────────────────────────────────────────────

def get_pricing_forecast(base_rate: float, lot_id: int) -> list:
    """Return 24-hour pricing forecast for a lot."""
    engine = DynamicPricingEngine()
    today  = datetime.now()
    dow    = today.weekday()
    # Simulate occupancy curve by hour
    occ_curve = {
        0: 15, 1: 10, 2: 8,  3: 8,  4: 12, 5: 20,
        6: 40, 7: 65, 8: 82, 9: 88, 10: 85, 11: 80,
        12: 78, 13: 75, 14: 70, 15: 72, 16: 80, 17: 90,
        18: 88, 19: 75, 20: 55, 21: 40, 22: 25, 23: 18,
    }
    result = []
    for h in range(24):
        occ = occ_curve.get(h, 50)
        pricing = engine.calculate_price(base_rate, occ, h, dow)
        result.append({
            'hour':         h,
            'hour_label':   f"{h:02d}:00",
            'occupancy_pct': occ,
            **pricing,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7. Group Booking (reserve multiple slots)
# ─────────────────────────────────────────────────────────────────────────────

def create_group_booking_plan(lot_slots: list, group_size: int,
                               preferences: dict = None) -> dict:
    """
    Given available slots, plan a group booking for N cars.
    Returns contiguous/nearby slots for a group.
    """
    available = [s for s in lot_slots if s.get('status') == 'available']
    if len(available) < group_size:
        return {'success': False, 'message': f'Only {len(available)} slots available, need {group_size}'}

    recommender = SlotRecommender()
    # Sort by row then number for contiguity
    available.sort(key=lambda s: s.get('slot_code', 'Z9'))
    selected = available[:group_size]

    total_score = sum(recommender.score_slot(s['slot_code'], preferences or {})
                      for s in selected)

    return {
        'success':     True,
        'group_size':  group_size,
        'slots':       [s['slot_code'] for s in selected],
        'slot_ids':    [s['id'] for s in selected],
        'group_score': round(total_score / group_size, 1),
        'message':     f'✅ {group_size} contiguous slots reserved for your group!',
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Smart Waitlist System
# ─────────────────────────────────────────────────────────────────────────────

class WaitlistManager:
    """
    In-memory waitlist (production: store in DB table `waitlist`).
    Notifies next user when a slot becomes available.
    """
    _queue: list = []   # list of dicts: {user_id, lot_id, added_at, preferences}

    def add(self, user_id: int, lot_id: int, preferences: dict = None) -> dict:
        entry = {
            'user_id':    user_id,
            'lot_id':     lot_id,
            'added_at':   datetime.now().isoformat(),
            'preferences': preferences or {},
            'position':   len([e for e in self._queue if e['lot_id'] == lot_id]) + 1,
        }
        self._queue.append(entry)
        eta_minutes = entry['position'] * 15  # rough ETA
        return {
            'position':    entry['position'],
            'eta_minutes': eta_minutes,
            'message':     f"You're #{entry['position']} in line. Est. wait: ~{eta_minutes} min.",
        }

    def notify_next(self, lot_id: int) -> dict | None:
        for entry in self._queue:
            if entry['lot_id'] == lot_id:
                self._queue.remove(entry)
                return entry
        return None

    def position(self, user_id: int, lot_id: int) -> int:
        for i, e in enumerate(self._queue):
            if e['user_id'] == user_id and e['lot_id'] == lot_id:
                return i + 1
        return -1

waitlist = WaitlistManager()


# ─────────────────────────────────────────────────────────────────────────────
# 9. EV Charging Slot Management
# ─────────────────────────────────────────────────────────────────────────────

EV_CHARGER_RATE_KW = 7.4   # kW (standard AC charger)
EV_COST_PER_KWH    = 8.0   # ₹8 per kWh (approximate)

def calculate_ev_charging(duration_hours: float, battery_pct_start: float = 20,
                           battery_capacity_kwh: float = 40.0) -> dict:
    energy_needed = battery_capacity_kwh * (1 - battery_pct_start / 100)
    charge_hours  = min(duration_hours, energy_needed / EV_CHARGER_RATE_KW)
    energy_added  = round(charge_hours * EV_CHARGER_RATE_KW, 2)
    cost          = round(energy_added * EV_COST_PER_KWH, 2)
    battery_end   = min(100, round(battery_pct_start + (energy_added / battery_capacity_kwh) * 100, 1))
    range_added   = round(energy_added * 6, 1)  # ~6 km per kWh

    return {
        'charger_kw':          EV_CHARGER_RATE_KW,
        'duration_hours':      duration_hours,
        'charge_hours':        round(charge_hours, 2),
        'energy_added_kwh':    energy_added,
        'charging_cost_inr':   cost,
        'battery_start_pct':   battery_pct_start,
        'battery_end_pct':     battery_end,
        'range_added_km':      range_added,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. Per-User Parking Analytics
# ─────────────────────────────────────────────────────────────────────────────

def compute_user_analytics(bookings: list) -> dict:
    """
    Given a list of booking dicts for a user, return rich analytics.
    """
    if not bookings:
        return {'message': 'No bookings found.'}

    total_spent    = sum(b.get('amount', 0) for b in bookings)
    total_hours    = sum(b.get('duration_hours', 1) for b in bookings)
    total_bookings = len(bookings)
    avg_duration   = round(total_hours / total_bookings, 1)

    # Favourite lot
    lot_counts = {}
    for b in bookings:
        name = b.get('lot_name', 'Unknown')
        lot_counts[name] = lot_counts.get(name, 0) + 1
    favourite_lot = max(lot_counts, key=lot_counts.get) if lot_counts else 'N/A'

    # Booking by day of week
    dow_counts = {d: 0 for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']}
    for b in bookings:
        try:
            dt  = datetime.strptime(b['booking_date'], '%Y-%m-%d')
            day = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.weekday()]
            dow_counts[day] += 1
        except Exception:
            pass
    busiest_day = max(dow_counts, key=dow_counts.get)

    carbon = calculate_carbon_savings(total_bookings, avg_duration)

    return {
        'total_bookings':   total_bookings,
        'total_spent_inr':  round(total_spent, 2),
        'total_hours':      total_hours,
        'avg_duration_hrs': avg_duration,
        'favourite_lot':    favourite_lot,
        'busiest_day':      busiest_day,
        'dow_distribution': dow_counts,
        'carbon_impact':    carbon,
        'loyalty_points':   int(total_spent),  # 1 pt per ₹1
        'loyalty_status':   get_loyalty_status(int(total_spent)),
    }
