import json
import os
import threading
from datetime import datetime

import customtkinter as ctk
import requests

# ---------- Colours (futuristic neon theme) ----------
BG = "#070b14"
PANEL = "#0d1424"
CYAN = "#00f0ff"
PINK = "#ff2e97"
TEXT = "#e6f1ff"
MUTED = "#6b7a99"

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# history.json is saved next to this file
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

ctk.set_appearance_mode("dark")


class WeatherError(Exception):
    """Used for friendly error messages."""
    pass


def load_history():
    """Read the list of recent cities from disk."""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (OSError, ValueError):
        pass
    return []


def save_history(cities):
    """Write the list of recent cities to disk."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(cities, f)
    except OSError:
        pass


def get_coordinates(city):
    """Turn a city name into latitude and longitude."""
    try:
        r = requests.get(GEO_URL, params={"name": city, "count": 1}, timeout=10)
        r.raise_for_status()
    except requests.RequestException:
        raise WeatherError("NETWORK ERROR - CHECK YOUR INTERNET")

    results = r.json().get("results")
    if not results:
        raise WeatherError("LOCATION '" + city.upper() + "' NOT FOUND")
    place = results[0]
    name = place["name"] + ", " + place.get("country", "")
    return place["latitude"], place["longitude"], name


def get_weather(lat, lon):
    """Get current weather and a 5-day forecast (always in Celsius, km/h)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,sunrise,sunset",
        "timezone": "auto",
        "forecast_days": 5,
    }
    try:
        r = requests.get(WEATHER_URL, params=params, timeout=10)
        r.raise_for_status()
    except requests.RequestException:
        raise WeatherError("COULD NOT FETCH WEATHER DATA")
    return r.json()


def code_to_icon(code):
    """Return (symbol, colour, description) for a weather code."""
    if code == 0:
        return "☀", "#ffd60a", "CLEAR SKY"
    if code in (1, 2, 3):
        return "☁", "#8ecae6", "CLOUDY"
    if code in (45, 48):
        return "≋", "#9aa5b1", "FOG"
    if 51 <= code <= 67:
        return "☂", "#00b4ff", "RAIN"
    if 71 <= code <= 77:
        return "❄", "#ffffff", "SNOW"
    if 80 <= code <= 82:
        return "☂", "#00b4ff", "SHOWERS"
    if code >= 95:
        return "⚡", PINK, "THUNDERSTORM"
    return "◌", MUTED, "UNKNOWN"


class WeatherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WEATHER // DASHBOARD")
        self.geometry("800x780")
        self.minsize(740, 740)
        self.configure(fg_color=BG)

        # App memory
        self.unit = "C"
        self.last_name = None
        self.last_data = None
        self.loading = False
        self.dots = 0
        self.history = load_history()

        mono = "Consolas"

        # ----- Header -----
        ctk.CTkLabel(
            self, text="WEATHER // DASHBOARD", text_color=CYAN,
            font=ctk.CTkFont(family=mono, size=26, weight="bold"),
        ).pack(pady=(20, 0))
        ctk.CTkLabel(
            self, text="REAL-TIME ATMOSPHERIC DATA", text_color=MUTED,
            font=ctk.CTkFont(family=mono, size=12),
        ).pack(pady=(0, 12))

        # ----- Search bar -----
        search = ctk.CTkFrame(self, fg_color="transparent")
        search.pack(pady=5)
        self.entry = ctk.CTkEntry(
            search, width=360, height=42, placeholder_text="ENTER CITY...",
            fg_color=PANEL, border_color=CYAN, border_width=2,
            text_color=TEXT, corner_radius=10,
            font=ctk.CTkFont(family=mono, size=15),
        )
        self.entry.pack(side="left", padx=(0, 10))
        self.entry.bind("<Return>", lambda event: self.search())
        ctk.CTkButton(
            search, text="SCAN", width=90, height=42, corner_radius=10,
            fg_color=CYAN, hover_color="#7df9ff", text_color=BG,
            font=ctk.CTkFont(family=mono, size=15, weight="bold"),
            command=self.search,
        ).pack(side="left", padx=(0, 10))

        # °C / °F switch
        self.unit_switch = ctk.CTkSegmentedButton(
            search, values=["°C", "°F"], command=self.change_unit,
            width=110, height=42, corner_radius=10,
            fg_color=PANEL, selected_color=PINK, selected_hover_color="#ff5cb0",
            unselected_color=PANEL, unselected_hover_color="#1a2540",
            text_color=TEXT, font=ctk.CTkFont(family=mono, size=14, weight="bold"),
        )
        self.unit_switch.set("°C")
        self.unit_switch.pack(side="left")

        # ----- Recent searches -----
        self.history_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.history_frame.pack(pady=(8, 0))
        self.refresh_history()

        self.status = ctk.CTkLabel(
            self, text="> AWAITING INPUT", text_color=MUTED,
            font=ctk.CTkFont(family=mono, size=13),
        )
        self.status.pack(pady=(8, 6))

        # ----- Main card -----
        self.main_card = ctk.CTkFrame(
            self, fg_color=PANEL, border_color=CYAN, border_width=2,
            corner_radius=18,
        )
        self.main_card.pack(padx=30, pady=8, fill="x")

        self.city_label = ctk.CTkLabel(
            self.main_card, text="--", text_color=TEXT,
            font=ctk.CTkFont(family=mono, size=22, weight="bold"),
        )
        self.city_label.pack(pady=(14, 0))

        self.icon_label = ctk.CTkLabel(
            self.main_card, text="◌", text_color=MUTED,
            font=ctk.CTkFont(family="Segoe UI Symbol", size=54),
        )
        self.icon_label.pack()

        self.temp_label = ctk.CTkLabel(
            self.main_card, text="--°C", text_color=CYAN,
            font=ctk.CTkFont(family=mono, size=60, weight="bold"),
        )
        self.temp_label.pack()

        self.desc_label = ctk.CTkLabel(
            self.main_card, text="NO DATA", text_color=PINK,
            font=ctk.CTkFont(family=mono, size=15, weight="bold"),
        )
        self.desc_label.pack(pady=(0, 10))

        stats = ctk.CTkFrame(self.main_card, fg_color="transparent")
        stats.pack(pady=(0, 14))
        self.humidity_label = self.make_stat(stats, "HUMIDITY", 0)
        self.wind_label = self.make_stat(stats, "WIND", 1)
        self.feels_label = self.make_stat(stats, "FEELS LIKE", 2)
        self.sunrise_label = self.make_stat(stats, "SUNRISE", 3)
        self.sunset_label = self.make_stat(stats, "SUNSET", 4)

        # ----- Forecast row -----
        ctk.CTkLabel(
            self, text="// 5-DAY FORECAST", text_color=MUTED,
            font=ctk.CTkFont(family=mono, size=12),
        ).pack(pady=(10, 2))
        self.forecast_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.forecast_frame.pack(padx=30, pady=4, fill="x")

    # ---------- Small helpers ----------
    def make_stat(self, parent, title, column):
        box = ctk.CTkFrame(
            parent, fg_color=BG, border_color=PINK, border_width=1,
            corner_radius=10,
        )
        box.grid(row=0, column=column, padx=5)
        ctk.CTkLabel(
            box, text=title, text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=11),
        ).pack(padx=16, pady=(8, 0))
        value = ctk.CTkLabel(
            box, text="--", text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=17, weight="bold"),
        )
        value.pack(pady=(0, 8))
        return value

    def temp(self, celsius):
        """Convert a Celsius number into the chosen unit."""
        if self.unit == "F":
            return round(celsius * 9 / 5 + 32, 1)
        return celsius

    def wind(self, kmh):
        """Convert km/h into the chosen unit."""
        if self.unit == "F":
            return str(round(kmh * 0.621371, 1)) + " mph"
        return str(kmh) + " km/h"

    # ---------- Recent searches ----------
    def refresh_history(self):
        for widget in self.history_frame.winfo_children():
            widget.destroy()
        if not self.history:
            return
        ctk.CTkLabel(
            self.history_frame, text="RECENT:", text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).pack(side="left", padx=(0, 6))
        for city in self.history:
            ctk.CTkButton(
                self.history_frame, text=city.upper(), width=10, height=26,
                corner_radius=13, fg_color=PANEL, hover_color="#1a2540",
                border_color=CYAN, border_width=1, text_color=CYAN,
                font=ctk.CTkFont(family="Consolas", size=12),
                command=lambda c=city: self.search_city(c),
            ).pack(side="left", padx=3)

    def add_history(self, city):
        # Remove if already there, then put it first
        self.history = [c for c in self.history if c.lower() != city.lower()]
        self.history.insert(0, city)
        self.history = self.history[:5]
        save_history(self.history)
        self.refresh_history()

    def search_city(self, city):
        self.entry.delete(0, "end")
        self.entry.insert(0, city)
        self.search()

    # ---------- Unit switch ----------
    def change_unit(self, value):
        self.unit = "F" if value == "°F" else "C"
        if self.last_data:
            self.render()

    # ---------- Searching ----------
    def search(self):
        if self.loading:
            return
        city = self.entry.get().strip()
        if not city:
            self.status.configure(text="> PLEASE ENTER A CITY", text_color=PINK)
            return
        self.loading = True
        self.dots = 0
        self.animate()
        # Run in the background so the window doesn't freeze
        threading.Thread(target=self.fetch, args=(city,), daemon=True).start()

    def animate(self):
        """Animated 'SCANNING...' text and pulsing border while loading."""
        if not self.loading:
            return
        self.dots = (self.dots + 1) % 4
        self.status.configure(text="> SCANNING" + "." * self.dots, text_color=CYAN)
        pulse = PINK if self.dots % 2 == 0 else CYAN
        self.main_card.configure(border_color=pulse)
        self.after(250, self.animate)

    def fetch(self, city):
        try:
            lat, lon, name = get_coordinates(city)
            data = get_weather(lat, lon)
            self.after(0, self.show, name, data)
        except WeatherError as error:
            self.after(0, self.show_error, str(error))

    def show_error(self, message):
        self.loading = False
        self.main_card.configure(border_color=CYAN)
        self.status.configure(text="> " + message, text_color=PINK)

    def show(self, name, data):
        self.loading = False
        self.main_card.configure(border_color=CYAN)
        self.last_name = name
        self.last_data = data
        self.add_history(name.split(",")[0])
        self.status.configure(text="> SCAN COMPLETE", text_color=CYAN)
        self.render()

    def render(self):
        """Draw the data on screen (also used when switching units)."""
        data = self.last_data
        cur = data["current"]
        daily = data["daily"]
        symbol, color, desc = code_to_icon(cur["weather_code"])

        self.city_label.configure(text=self.last_name.upper())
        self.icon_label.configure(text=symbol, text_color=color)
        self.temp_label.configure(text=str(self.temp(cur["temperature_2m"])) + "°" + self.unit)
        self.desc_label.configure(text=desc)
        self.humidity_label.configure(text=str(cur["relative_humidity_2m"]) + "%")
        self.wind_label.configure(text=self.wind(cur["wind_speed_10m"]))
        self.feels_label.configure(text=str(self.temp(cur["apparent_temperature"])) + "°")
        self.sunrise_label.configure(text=daily["sunrise"][0][11:16])
        self.sunset_label.configure(text=daily["sunset"][0][11:16])

        # Clear old forecast cards
        for widget in self.forecast_frame.winfo_children():
            widget.destroy()

        for i, day in enumerate(daily["time"]):
            self.forecast_frame.grid_columnconfigure(i, weight=1, uniform="cards")
            card = ctk.CTkFrame(
                self.forecast_frame, fg_color=PANEL, border_color=CYAN,
                border_width=1, corner_radius=12,
            )
            card.grid(row=0, column=i, padx=5, sticky="nsew")

            day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%a").upper()
            sym, col, _ = code_to_icon(daily["weather_code"][i])

            ctk.CTkLabel(
                card, text=day_name, text_color=MUTED,
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            ).pack(pady=(10, 0))
            ctk.CTkLabel(
                card, text=sym, text_color=col,
                font=ctk.CTkFont(family="Segoe UI Symbol", size=30),
            ).pack()
            ctk.CTkLabel(
                card, text=str(self.temp(daily["temperature_2m_max"][i])) + "°",
                text_color=PINK,
                font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            ).pack()
            ctk.CTkLabel(
                card, text=str(self.temp(daily["temperature_2m_min"][i])) + "°",
                text_color=CYAN,
                font=ctk.CTkFont(family="Consolas", size=14),
            ).pack(pady=(0, 10))


if __name__ == "__main__":
    WeatherApp().mainloop()