# ✈️ VoyageAI — Multi-Agent AI Travel Planner

VoyageAI is an AI-powered travel planning system that converts natural-language trip requests into personalized, route-aware, multi-day itineraries.

Unlike a basic AI travel chatbot, VoyageAI combines destination research, weather context, real-place resolution, routing, and mathematical optimization using Google OR-Tools.

The final itinerary is displayed through a React interface with timed activities, travel information, and an interactive Leaflet/OpenStreetMap map.

---

## 🚀 Project Overview

A user can describe a trip naturally, for example:

> Plan a trip from Hyderabad to Tokyo from 10 December 2026 to 16 December 2026 for 2 people. My total budget is 200000 rupees. I like anime, technology and Japanese food.

VoyageAI then performs the following workflow:

1. Understands the natural-language request
2. Extracts destination, dates, travelers, budget and interests
3. Researches the destination
4. Generates personalized recommendations
5. Evaluates weather suitability
6. Converts recommendations into structured activities
7. Resolves activities to real geographic locations
8. Calculates travel times and routes
9. Optimizes the itinerary using Google OR-Tools
10. Generates start and end times
11. Displays the itinerary on an interactive map

---

## 🎯 Problem Statement

Planning a trip usually requires multiple applications and websites for:

- Destination research
- Weather information
- Maps
- Attraction discovery
- Travel-time calculation
- Daily scheduling
- Budget planning

AI chatbots can generate travel recommendations, but the resulting itinerary may not always be geographically or temporally practical.

VoyageAI solves this problem by combining AI-generated destination intelligence with real geographic information, route calculations and mathematical optimization.

The goal is to produce an itinerary that is:

- Personalized
- Route-aware
- Weather-aware
- Time-constrained
- Optimized
- Easy to visualize

---

## 🧠 System Architecture

```text
Natural Language Trip Request
            │
            ▼
     React + Vite Frontend
            │
            ▼
        FastAPI API
            │
            ▼
     Request Understanding
            │
            ▼
  Destination Research Agent
            │
     ┌──────┴──────┐
     ▼             ▼
 Web Research    Gemini
     │             │
     └──────┬──────┘
            ▼
 Structured Recommendations
            │
            ▼
    Activity Intelligence
            │
     ┌──────┴──────┐
     ▼             ▼
Weather Outlook  Preference /
                 Confidence
     │             │
     └──────┬──────┘
            ▼
      Place Resolution
            │
            ▼
   Latitude / Longitude
            │
            ▼
       Routing Service
            │
            ▼
    Travel-Time Matrix
            │
            ▼
     Google OR-Tools
            │
            ▼
   Optimized Itinerary
            │
            ▼
 React + Leaflet Visualization