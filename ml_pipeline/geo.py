
#Geofencing and location utilities for TRACE



"""
  1. eucledian()              — distance in metres between two GPS points
  2. nearest_office()         — find the closest municipality office to a camera
  3. in_high_sensitivity_zone() — check if a camera is inside a protected zone
  4. get_geo_skip()           — priority floor for cameras in sensitive zones

"""

import math
from config import MUNICIPALITY_OFFICES, HIGH_SENSITIVITY_ZONES
from config import PRIORITY_MEDIUM_SKIP


def eucledian(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat   = (lat2 - lat1)
    dlng   = (lng2 - lng1)

    return math.sqrt(dlat**2 + dlng**2)


def nearest_office(cam_lat: float, cam_lng: float) -> dict | None:
    if not MUNICIPALITY_OFFICES:
        return None

    return min(
        MUNICIPALITY_OFFICES,
        key=lambda o: eucledian(cam_lat, cam_lng, o["lat"], o["lng"])
    )


def in_high_sensitivity_zone(cam_lat: float, cam_lng: float) -> str | None:
   
    for zone in HIGH_SENSITIVITY_ZONES:
        dist = eucledian(cam_lat, cam_lng, zone["lat"], zone["lng"])
        if dist <= zone["radius_m"]:
            return zone["name"]
    return None


def get_geo_skip(current_skip: int, cam_lat: float, cam_lng: float) -> int:

    zone_name = in_high_sensitivity_zone(cam_lat, cam_lng)
    if zone_name and current_skip > PRIORITY_MEDIUM_SKIP:
        print(f"[GEO] Sensitivity zone '{zone_name}' — holding at MEDIUM")
        return PRIORITY_MEDIUM_SKIP
    return current_skip