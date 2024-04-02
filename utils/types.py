from typing import NotRequired, TypedDict


class ErrorDict(TypedDict):
    code: int
    message: str


class LocationDict(TypedDict):
    name: str
    region: str
    country: str
    lat: float
    lon: float
    tz_id: str
    localtime_epoch: int
    localtime: str


class ConditionDict(TypedDict):
    text: str
    icon: str
    code: int


class CurrentDict(TypedDict):
    last_updated_epoch: int
    last_updated: str
    temp_c: float
    temp_f: float
    is_day: int
    condition: ConditionDict
    wind_mph: float
    wind_kph: float
    wind_degree: int
    wind_dir: str
    pressure_mb: float
    pressure_in: float
    precip_mm: float
    precip_in: float
    humidity: int
    cloud: int
    feelslike_c: float
    feelslike_f: float
    vis_km: float
    vis_miles: float
    uv: float
    gust_mph: float
    gust_kph: float


class WeatherDict(TypedDict):
    error: NotRequired[ErrorDict]
    location: LocationDict
    current: CurrentDict


class UrbanData(TypedDict):
    definition: str
    permalink: str
    thumbs_up: int
    author: str
    word: str
    defid: int
    current_vote: str
    written_on: str
    example: str
    thumbs_down: int
