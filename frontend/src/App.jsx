import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle, ArrowLeft, ArrowRight, CalendarDays, Check, CheckCircle2,
  ChevronDown, Clock3, CloudSun, Compass, Eye, EyeOff, Globe2, Heart, KeyRound,
  Layers3, LoaderCircle, LockKeyhole, LogOut, MapPin, Menu, Plane, Route as RouteIcon,
  ShieldCheck, Sparkles, Sun, Users, Wallet, X,
} from 'lucide-react'
import TripMap from './components/TripMap'
import BudgetEditor from './components/BudgetEditor'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import { apiRequest } from './lib/api'
import { getOrderedRouteStops, getRouteLegMinutes, getRouteTotalMinutes } from './lib/routeData'
import { getActiveNavigationItem } from './lib/navigation'
import DestinationImage from './components/DestinationImage'
import './App.css'

const TripContext = createContext(null)
const dates = (start, end) => start && end ? `${new Date(`${start}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${new Date(`${end}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}` : 'Dates to be confirmed'
const money = (amount, currency = 'JPY') => amount == null ? 'Not available' : new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(amount))
const titleCase = value => (value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())

function useTrip() {
  return useContext(TripContext)
}

function useVoyageApi() {
  const { session } = useAuth()
  return useCallback((path, options = {}) => apiRequest(path, { ...options, token: session?.access_token }), [session?.access_token])
}

function PrivateRoute({ children }) {
  const { user, loading, configured } = useAuth()
  const localPreview = import.meta.env.DEV && !configured
  if (loading) return <LoadingScreen label="Restoring your secure session" />
  return user || localPreview ? children : <Navigate to="/login" replace />
}

function Header() {
  const { user, signOut, configured } = useAuth()
  const { trip } = useTrip()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const activeNavigationItem = getActiveNavigationItem(pathname)
  const activeTrip = trip?.trip_id
  const itineraryUrl = activeTrip ? `/trips/${activeTrip}/itinerary` : '/my-trips'
  const mapUrl = activeTrip ? `/trips/${activeTrip}/map` : '/my-trips'
  const closeMenu = () => setMenuOpen(false)
  const navigationLink = (key, to, label) => <Link
    to={to}
    className={activeNavigationItem === key ? 'active' : undefined}
    aria-current={activeNavigationItem === key ? 'page' : undefined}
    onClick={closeMenu}
  >{label}</Link>
  return <header className="site-header">
    <Link className="brand" to="/" aria-label="VoyageAI home" onClick={closeMenu}><span className="brand-mark"><Compass size={21} /></span><span>voyage<span>ai</span></span></Link>
    <nav className={`main-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Main navigation">
      {navigationLink('home', '/', 'Home')}
      {navigationLink('plan', '/plan-trip', 'Plan a Trip')}
      {navigationLink('budget', activeTrip ? `/trips/${activeTrip}/budget` : '/my-trips', 'Budget Review')}
      {navigationLink('itinerary', itineraryUrl, 'My Itinerary')}
      {navigationLink('map', mapUrl, 'Trip Map')}
      {user && navigationLink('trips', '/my-trips', 'My Trips')}
    </nav>
    <div className="header-account">
      {user ? <details className="account-menu"><summary aria-label="Account menu"><span className="avatar">{user.email?.[0]?.toUpperCase() || 'V'}</span><ChevronDown size={15} /></summary><div className="account-dropdown"><span className="account-email">{user.email}</span><Link to="/account">Account settings</Link><button onClick={() => { signOut(); closeMenu() }}><LogOut size={15} />Sign out</button></div></details>
        : <Link className="sign-in-link" to="/login">{configured ? 'Sign in' : 'Account'} <ArrowRight size={15} /></Link>}
      <button className="mobile-menu" onClick={() => setMenuOpen(open => !open)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}>{menuOpen ? <X size={21} /> : <Menu size={21} />}</button>
    </div>
  </header>
}

function SiteLayout({ children }) {
  return <div className="app-shell"><Header />{children}<footer className="site-footer"><Link className="brand" to="/"><span className="brand-mark"><Compass size={18} /></span><span>voyage<span>ai</span></span></Link><p>Thoughtful journeys begin here.</p><span>© 2026 VoyageAI</span></footer></div>
}

function LoadingScreen({ label = 'Loading your trip' }) {
  return <div className="loading-screen"><span className="loading-mark"><LoaderCircle size={24} className="spin" /></span><p>{label}</p></div>
}

function HomePage() {
  const features = [
    { icon: <Layers3 />, title: 'Multi-agent planning', body: 'AI agents research places, costs, weather and routes together.' },
    { icon: <Wallet />, title: 'Budget aware', body: 'Review sourced estimates and set your own category limits.' },
    { icon: <MapPin />, title: 'Personalized itinerary', body: 'Your interests shape a practical, day-by-day plan.' },
    { icon: <CalendarDays />, title: 'All in one place', body: 'Move from planning to an itinerary and interactive map.' },
  ]
  const places = [
    { name: 'Kyoto, Japan', type: 'Culture', detail: 'Temples, gardens and timeless culture.', image: 'photo-1493976040374-85c8e12f0c0e' },
    { name: 'Amalfi Coast, Italy', type: 'Coastal', detail: 'Coastal charm, scenic views and great food.', image: 'photo-1533105079780-92b9be482077' },
    { name: 'Marrakech, Morocco', type: 'City break', detail: 'Vibrant markets, rich history and colorful streets.', image: 'photo-1539020140153-e479b8c22e70' },
  ]
  return <SiteLayout>
    <main>
      <section className="home-hero">
        <div className="hero-copy"><div className="eyebrow"><span /> AI-POWERED TRAVEL PLANNING</div><h1>Your journey,<br /><em>beautifully organized.</em></h1><p>Plan smarter trips with a team of AI travel agents — compare costs, discover the best places, and get a personalized itinerary built around your budget, interests, and travel style.</p><Link className="primary-button" to="/plan-trip"><Plane size={19} /> Plan my journey <ArrowRight size={18} /></Link></div>
        <div className="hero-visual" role="img" aria-label="Kyoto pagoda and cherry blossoms at sunset" />
      </section>
      <section className="feature-ribbon" aria-label="VoyageAI features">{features.map(item => <article key={item.title}><span className="feature-icon">{item.icon}</span><div><strong>{item.title}</strong><p>{item.body}</p></div></article>)}</section>
      <section className="inspiration-section"><div className="section-heading"><div><div className="eyebrow"><span /> GET INSPIRED</div><h2>Discover <em>destinations</em></h2></div><Link to="/plan-trip" className="text-link">Explore your next trip <ArrowRight size={16} /></Link></div><div className="destination-grid">{places.map(place => <article className="destination-card" key={place.name}><div className="destination-photo" style={{ backgroundImage: `url(https://images.unsplash.com/${place.image}?auto=format&fit=crop&w=1000&q=85)` }}><span className="destination-tag"><Globe2 size={14} />{place.type}</span><button className="favorite-button" aria-label={`Save ${place.name}`} onClick={event => event.currentTarget.classList.toggle('is-saved')}><Heart size={18} /></button><div className="destination-caption"><h3>{place.name}</h3><p>{place.detail}</p></div></div></article>)}</div></section>
      <section className="how-section"><div className="eyebrow"><span /> A BETTER WAY TO PLAN</div><h2>More seeing.<br /><em>Less searching.</em></h2><p>Research, costs, routes and weather come together around your own travel priorities. You stay in control of the budget before VoyageAI builds the itinerary.</p><Link to="/plan-trip" className="text-link">Start with your trip details <ArrowRight size={16} /></Link></section>
    </main>
  </SiteLayout>
}

function PlanTripPage() {
  const { setTrip } = useTrip()
  const api = useVoyageApi()
  const navigate = useNavigate()
  const [form, setForm] = useState({ origin: '', destination: '', departure: '', returnDate: '', travelers: 2, budget: '', currency: 'JPY', interests: [], notes: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [clarification, setClarification] = useState(null)
  const [clarificationAnswer, setClarificationAnswer] = useState('')
  const interests = ['Sightseeing', 'Culture', 'Temples', 'Nature', 'Local food', 'Architecture', 'Shopping', 'Adventure']
  const change = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const toggleInterest = interest => change('interests', form.interests.includes(interest) ? form.interests.filter(item => item !== interest) : [...form.interests, interest])

  async function submit(event) {
    event.preventDefault()
    setLoading(true); setError(''); setClarification(null)
    const request = `Plan a trip from ${form.origin} to ${form.destination}. Departure ${form.departure}; return ${form.returnDate}. There are ${form.travelers} travellers. Total trip budget ${form.currency} ${form.budget}. Interests: ${form.interests.join(', ') || 'general sightseeing'}.${form.notes ? ` Additional preferences: ${form.notes}` : ''}`
    try {
      const result = await api('/api/plan-trip', { method: 'POST', body: { request } })
      setTrip(result)
      if (result.status === 'budget_review') navigate(`/trips/${result.trip_id}/budget`)
      else if (result.status === 'needs_clarification' || result.clarification) setClarification(result)
      else if (result.trip_id) navigate(`/trips/${result.trip_id}/itinerary`)
      else setError('The planner did not return a trip identifier. Please try again or contact support.')
    } catch (reason) { setError(reason.message || 'VoyageAI could not start your plan.') }
    finally { setLoading(false) }
  }

  async function continueClarification(event) {
    event.preventDefault()
    if (!clarification?.thread_id || !clarificationAnswer.trim()) return
    setLoading(true); setError('')
    try {
      const result = await api('/api/resume-trip', {
        method: 'POST',
        body: { thread_id: clarification.thread_id, answer: clarificationAnswer.trim() },
      })
      setTrip(result)
      setClarificationAnswer('')
      if (result.status === 'budget_review') navigate(`/trips/${result.trip_id}/budget`)
      else if (result.status === 'needs_clarification' || result.clarification) setClarification(result)
      else if (result.status === 'complete' && result.trip_id) navigate(`/trips/${result.trip_id}/itinerary`)
      else setClarification(result)
    } catch (reason) { setError(reason.message || 'VoyageAI could not continue this trip.') }
    finally { setLoading(false) }
  }

  return <SiteLayout><main className="page-main"><div className="page-intro"><div className="eyebrow"><span /> YOUR PERSONAL TRAVEL DESK</div><h1>Let’s plan a journey <em>that feels like yours.</em></h1><p>Share the essentials and your interests. You’ll review the researched budget before the itinerary is built.</p></div>
    {clarification && <section className="clarification-panel"><div className="notice-icon"><Sparkles size={18} /></div><div><strong>One more detail</strong><p>{clarification.clarification?.question || clarification.clarification?.message || 'The travel team needs one more detail to continue.'}</p><form className="clarification-form" onSubmit={continueClarification}><label htmlFor="clarification-answer">Your answer</label><div><input id="clarification-answer" required value={clarificationAnswer} onChange={event => setClarificationAnswer(event.target.value)} placeholder="Add the missing trip detail" /><button className="primary-button" disabled={loading}>{loading ? <LoaderCircle size={16} className="spin" /> : <>Continue planning <ArrowRight size={16} /></>}</button></div></form></div></section>}
    <form className="trip-form panel-card" onSubmit={submit}>
      <div className="form-section-title"><span>01</span><div><h2>The journey</h2><p>Where are you starting and where would you like to go?</p></div></div>
      <div className="form-grid two"><label>Starting from<input required value={form.origin} onChange={event => change('origin', event.target.value)} placeholder="Hyderabad, India" autoComplete="address-level2" /></label><label>Destination<input required value={form.destination} onChange={event => change('destination', event.target.value)} placeholder="Kyoto, Japan" /></label></div>
      <div className="form-section-title"><span>02</span><div><h2>Dates and travellers</h2><p>We’ll use the trip length to shape the daily plan and cost estimates.</p></div></div>
      <div className="form-grid four"><label>Departure<input required type="date" value={form.departure} onChange={event => change('departure', event.target.value)} /></label><label>Return<input required type="date" min={form.departure || undefined} value={form.returnDate} onChange={event => change('returnDate', event.target.value)} /></label><label>Travellers<select value={form.travelers} onChange={event => change('travelers', Number(event.target.value))}>{Array.from({ length: 8 }, (_, index) => index + 1).map(count => <option key={count} value={count}>{count} {count === 1 ? 'traveller' : 'travellers'}</option>)}</select></label><label>Currency<select value={form.currency} onChange={event => change('currency', event.target.value)}>{['JPY', 'INR', 'USD', 'EUR', 'GBP', 'CAD', 'AUD'].map(currency => <option key={currency}>{currency}</option>)}</select></label></div>
      <div className="form-section-title"><span>03</span><div><h2>Budget and interests</h2><p>Your total stays yours. Review every category before confirming.</p></div></div>
      <div className="form-grid two"><label>Total trip budget<input required type="number" min="1" step="1" value={form.budget} onChange={event => change('budget', event.target.value)} placeholder="180000" /></label><fieldset className="interest-picker"><legend>What are you interested in?</legend><div>{interests.map(item => <button type="button" key={item} className={form.interests.includes(item) ? 'interest-chip selected' : 'interest-chip'} onClick={() => toggleInterest(item)}>{form.interests.includes(item) && <Check size={13} />}{item}</button>)}</div></fieldset></div>
      <label className="full-field">Additional preferences<textarea rows="3" value={form.notes} onChange={event => change('notes', event.target.value)} placeholder="A slower pace, local food, accessibility needs, or places you have in mind…" /></label>
      {error && <div className="form-error" role="alert"><AlertCircle size={17} />{error}</div>}
      <div className="form-submit-row"><span><ShieldCheck size={16} /> Your budget won’t be confirmed without your review.</span><button className="primary-button" disabled={loading}>{loading ? <><LoaderCircle size={17} className="spin" /> Researching your trip…</> : <>Build my trip plan <ArrowRight size={17} /></>}</button></div>
    </form>
  </main></SiteLayout>
}

function useTripRecord() {
  const { tripId } = useParams()
  const { trip, setTrip } = useTrip()
  const api = useVoyageApi()
  const [loadedRecord, setLoadedRecord] = useState(null)
  const [loadState, setLoadState] = useState({ tripId: null, loading: true, error: '' })
  const record = trip?.trip_id === tripId ? trip : loadedRecord?.trip_id === tripId ? loadedRecord : null
  useEffect(() => {
    if (trip?.trip_id === tripId || loadedRecord?.trip_id === tripId) return undefined
    let cancelled = false
    api(`/api/trips/${tripId}`).then(saved => {
      if (!cancelled) {
        const restored = { ...saved.data, trip_id: saved.trip_id, thread_id: saved.thread_id, status: saved.status }
        setLoadedRecord(restored); setTrip(restored); setLoadState({ tripId, loading: false, error: '' })
      }
    }).catch(reason => { if (!cancelled) setLoadState({ tripId, loading: false, error: reason.message }) })
    return () => { cancelled = true }
  }, [api, tripId, trip?.trip_id, loadedRecord?.trip_id, setTrip])
  const updateTrip = useCallback(next => { setLoadedRecord(next); setTrip(next) }, [setTrip])
  const loading = !record && (loadState.tripId !== tripId || loadState.loading)
  const error = loadState.tripId === tripId ? loadState.error : ''
  return { trip: record, setTrip: updateTrip, loading, error, api }
}

function TripHero({ trip, eyebrow = 'YOUR TRIP PLAN', title }) {
  const finalTrip = trip?.final_trip || {}
  return <section className="trip-hero"><div className="trip-hero-backdrop" /><div className="trip-hero-copy"><div className="eyebrow"><span /> {eyebrow}</div><h1>{title || <>{finalTrip.destination || 'Your journey'} <em>itinerary</em></>}</h1><p>A thoughtful day-by-day plan shaped around your dates and interests.</p></div><div className="trip-summary-bar"><div><span><CalendarDays /></span><div><small>Travel dates</small><strong>{dates(finalTrip.departure_date, finalTrip.return_date)}</strong></div></div><div><span><Users /></span><div><small>Travellers</small><strong>{finalTrip.travelers || '—'} {finalTrip.travelers === 1 ? 'person' : 'people'}</strong></div></div><div><span><Wallet /></span><div><small>Total budget</small><strong>{money(finalTrip.budget, finalTrip.currency)}</strong></div></div><div><span><MapPin /></span><div><small>Destination</small><strong>{finalTrip.destination || 'To be confirmed'}</strong></div></div></div></section>
}

function BudgetReviewPage() {
  const { trip, setTrip, loading, error, api } = useTripRecord()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  if (loading) return <SiteLayout><LoadingScreen label="Restoring your budget review" /></SiteLayout>
  if (error || !trip) return <SiteLayout><EmptyState title="This trip isn’t available" body={error || 'The trip could not be found for this account.'} action="View my trips" to="/my-trips" /></SiteLayout>

  async function confirm(category_allocations, activity_costs, cost_option_selections) {
    setBusy(true); setActionError('')
    try {
      const result = await api('/api/confirm-budget', { method: 'POST', body: { thread_id: trip.thread_id, category_allocations, activity_costs, cost_option_selections } })
      setTrip(result)
      if (result.status === 'complete') navigate(`/trips/${trip.trip_id}/itinerary`)
      return result
    } catch (reason) { setActionError(reason.message); throw reason }
    finally { setBusy(false) }
  }

  async function regenerate() {
    setBusy(true); setActionError('')
    try {
      const result = await api('/api/regenerate-budget', { method: 'POST', body: { thread_id: trip.thread_id } })
      setTrip({ ...trip, ...result })
      return result
    } catch (reason) { setActionError(reason.message); throw reason }
    finally { setBusy(false) }
  }

  if (trip.status !== 'budget_review' || !trip.budget_allocation) return <SiteLayout><EmptyState title="Budget review is complete" body="This trip has moved beyond the budget checkpoint." action="Open itinerary" to={`/trips/${trip.trip_id}/itinerary`} /></SiteLayout>
  return <SiteLayout><main className="page-main trip-workspace"><TripHero trip={trip} eyebrow="STEP 2 · YOUR DECISION" title={<>Review your Kyoto <em>budget</em></>} /><div className="workflow-steps"><span className="done"><Check size={14} /> Trip details</span><i /><span className="active"><Wallet size={14} /> Budget review</span><i /><span><Sparkles size={14} /> Itinerary</span></div>{actionError && <div className="form-error"><AlertCircle size={17} />{actionError}</div>}<BudgetEditor allocation={trip.budget_allocation} costResearch={trip.cost_research} activities={trip.activity_intelligence?.activities || []} loading={busy} onConfirm={confirm} onRegenerate={regenerate} /></main></SiteLayout>
}

function TripClarificationPage() {
  const { trip, setTrip, loading, error, api } = useTripRecord()
  const navigate = useNavigate()
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  if (loading) return <SiteLayout><LoadingScreen label="Restoring your trip details" /></SiteLayout>
  if (error || !trip) return <SiteLayout><EmptyState title="This trip isn’t available" body={error || 'The trip could not be found for this account.'} action="View my trips" to="/my-trips" /></SiteLayout>
  const prompt = trip.clarification?.question || trip.clarification?.message
  if (trip.status !== 'needs_clarification' && !prompt) return <SiteLayout><EmptyState title="No details are needed" body="This trip has already moved past request clarification." action="Open trip" to={`/trips/${trip.trip_id}/${trip.status === 'budget_review' ? 'budget' : 'itinerary'}`} /></SiteLayout>

  async function resume(event) {
    event.preventDefault(); setBusy(true); setActionError('')
    try {
      const result = await api('/api/resume-trip', { method: 'POST', body: { thread_id: trip.thread_id, answer: answer.trim() } })
      setTrip(result)
      if (result.status === 'budget_review') navigate(`/trips/${result.trip_id}/budget`)
      else if (result.status === 'complete') navigate(`/trips/${result.trip_id}/itinerary`)
    } catch (reason) { setActionError(reason.message || 'VoyageAI could not continue this trip.') }
    finally { setBusy(false) }
  }

  return <SiteLayout><main className="page-main"><TripHero trip={trip} eyebrow="TRIP DETAILS" title={<>One more detail for <em>your journey</em></>} /><section className="panel-card clarification-page-card"><div className="notice-icon"><Sparkles size={20} /></div><div><h2>{prompt || 'The travel team needs one more detail to continue.'}</h2><p>Your answer resumes the saved planning conversation and keeps the trip details already provided.</p><form className="clarification-form" onSubmit={resume}><label htmlFor="trip-clarification-answer">Your answer</label><div><input id="trip-clarification-answer" required value={answer} onChange={event => setAnswer(event.target.value)} placeholder="Add the missing trip detail" /><button className="primary-button" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <>Continue planning <ArrowRight size={16} /></>}</button></div></form>{actionError && <div className="form-error" role="alert"><AlertCircle size={16} />{actionError}</div>}</div></section></main></SiteLayout>
}

function ItineraryPage() {
  const { trip, loading, error } = useTripRecord()
  const [activeDay, setActiveDay] = useState(1)
  const [routeData, setRouteData] = useState(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState(false)
  const itinerary = trip?.optimized_itinerary
  const days = itinerary?.days || []
  const day = days.find(item => item.day_number === activeDay) || days[0]
  const routeStops = getOrderedRouteStops(day, trip?.activity_intelligence?.activities || [])
  const routeMinutesByName = new Map(routeStops.map((stop, index) => [
    stop.name,
    getRouteLegMinutes(routeData, index, Math.max(routeStops.length - 1, 0)) ?? stop.travel_from_previous_minutes,
  ]))
  const routeTotalMinutes = getRouteTotalMinutes(routeData, day?.total_travel_minutes, Math.max(routeStops.length - 1, 0))
  const { session } = useAuth()

  useEffect(() => {
    if (!day) return undefined
    const places = getOrderedRouteStops(day, trip?.activity_intelligence?.activities || [])
    let cancelled = false
    if (places.length < 2) {
      queueMicrotask(() => { if (!cancelled) { setRouteData(null); setRouteError(false); setRouteLoading(false) } })
      return () => { cancelled = true }
    }
    queueMicrotask(() => { if (!cancelled) { setRouteData(null); setRouteError(false); setRouteLoading(true) } })
    fetch(`${import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : 'https://voyageai-backend-5pf8.onrender.com')}/api/route-geometry`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}) },
      body: JSON.stringify({ points: places.map(({ latitude, longitude }) => ({ latitude, longitude })) }),
    }).then(response => response.ok ? response.json() : Promise.reject(new Error('Route information is unavailable.')))
      .then(data => { if (!cancelled) setRouteData(data) })
      .catch(() => { if (!cancelled) { setRouteData(null); setRouteError(true) } })
      .finally(() => { if (!cancelled) setRouteLoading(false) })
    return () => { cancelled = true }
  }, [trip?.trip_id, day, trip?.activity_intelligence?.activities, session?.access_token])

  if (loading) return <SiteLayout><LoadingScreen label="Opening your itinerary" /></SiteLayout>
  if (error || !trip) return <SiteLayout><EmptyState title="This trip isn’t available" body={error || 'The trip could not be found for this account.'} action="View my trips" to="/my-trips" /></SiteLayout>
  if (!itinerary) return <SiteLayout><main className="page-main"><TripHero trip={trip} /><EmptyState title="Your itinerary is still being prepared" body="Complete the budget review first. The planning checkpoint keeps your trip details safe while you decide." action="Review budget" to={`/trips/${trip.trip_id}/budget`} /></main></SiteLayout>

  return <SiteLayout><main className="page-main trip-workspace"><TripHero trip={trip} title={<>Your {trip.final_trip?.destination || itinerary.destination} <em>itinerary</em></>} /><div className="itinerary-layout"><section className="itinerary-main"><div className="day-tabs" role="tablist" aria-label="Trip days">{days.map(item => <button key={item.day_number} role="tab" aria-selected={day?.day_number === item.day_number} className={day?.day_number === item.day_number ? 'active' : ''} onClick={() => setActiveDay(item.day_number)}><CalendarDays size={17} /><span>Day {item.day_number}<small>{formatTripDate(trip.final_trip?.departure_date, item.day_number - 1)}</small></span></button>)}</div>
      {itinerary.budget_status === 'provisional' && <div className="weather-warning"><AlertCircle size={19} /><p><strong>Provisional itinerary</strong><br />Some admission prices are unknown. They are excluded from priced totals, so total activity spending cannot be verified against your cap.</p></div>}
      {trip.weather_context?.data_mode === 'unavailable' && <div className="weather-warning"><CloudSun size={19} /><p><strong>Weather unavailable</strong><br />No forecast or seasonal conditions were available. No weather suitability is assumed.</p></div>}
      <article className="day-plan-card"><header><div><span className="eyebrow">DAY {day?.day_number}</span><h2>{day?.activities?.length ? `Explore ${trip.final_trip?.destination || 'your destination'}` : 'A day to discover'}</h2></div><span className="duration-chip"><Clock3 size={16} /> {Math.round((day?.total_activity_minutes || 0) / 60 * 10) / 10} hr visit estimates · {routeLoading ? 'calculating' : routeTotalMinutes != null ? `~${Math.round(routeTotalMinutes)} min driving` : 'driving unavailable'}{day?.buffer_minutes > 0 ? ` · ${day.buffer_minutes} min buffer` : ''}</span></header>
        {day?.schedule_note && day?.activities?.length > 0 && <p className="route-note"><ShieldCheck size={16} /> {day.schedule_note}</p>}
        {day?.activities?.length ? <ol className="activity-list">{day.activities.map((activity, index) => <li key={`${activity.name}-${index}`}><span className="activity-index">{String(index + 1).padStart(2, '0')}</span><div className="activity-copy"><h3>{activity.name}</h3><p>{activity.description || 'A suggested stop based on your trip interests.'}</p><div className="activity-meta"><span><Clock3 size={15} />~{activity.estimated_duration_minutes || '—'} min {activity.duration_estimate_basis === 'activity_specific_ai_estimate' ? 'activity estimate' : 'category estimate'}</span>{(routeMinutesByName.get(activity.name) ?? activity.travel_from_previous_minutes) > 0 && <span><RouteIcon size={15} />~{Math.round(routeMinutesByName.get(activity.name) ?? activity.travel_from_previous_minutes)} min driving estimate</span>}{activity.admission_status === 'verified_free' ? <span className="verified-pill"><CheckCircle2 size={14} /> Officially verified free</span> : activity.estimated_cost != null ? <span>{money(activity.estimated_cost, activity.currency)} · {activity.cost_status === 'user_provided' ? 'your estimate' : 'indicative'}</span> : <span className="unknown-pill">Admission price unknown</span>}</div>{activity.requires_price_verification && <small>Check admission price before visiting; this activity is not counted as free.</small>}</div><span className="category-pill">{titleCase(activity.category || 'Suggested stop')}</span></li>)}</ol> : <div className="empty-day"><Sun size={21} /><p>{day?.schedule_note || 'No activities were scheduled for this day. Check the saved trip details or regenerate the plan.'}</p></div>}
        <p className="route-note"><ShieldCheck size={16} /> Visit durations are planning estimates. A one-hour flexibility buffer is reserved on sightseeing days. Totals exclude meals, queues, parking and lodging/airport transfers; driving estimates are not public-transit times.</p>
      </article>
      <div className="day-navigation"><Link className="secondary-button" to={`/trips/${trip.trip_id}/budget`}><ArrowLeft size={16} /> Budget review</Link><Link className="secondary-button" to={`/trips/${trip.trip_id}/map`}>Explore the map <ArrowRight size={16} /></Link></div>
    </section>
    <aside className="itinerary-aside"><article className="route-summary-card"><div className="eyebrow"><RouteIcon size={15} /> ROUTE SUMMARY</div><div className="route-metrics"><div><MapPin /><strong>{day?.activities?.length || 0} stops</strong><small>for Day {day?.day_number || 1}</small></div><div><Clock3 /><strong>{routeLoading ? '…' : routeTotalMinutes != null ? `~ ${Math.round(routeTotalMinutes)} min` : 'Not available'}</strong><small>driving estimate</small></div></div><h3>Route (in order)</h3><ol className="route-order">{day?.activities?.map((activity, index) => <li key={`${activity.name}-${index}`}><span>{index + 1}</span><strong>{activity.name}</strong></li>)}</ol><p className="route-note"><ShieldCheck size={16} /> {routeError ? 'Live driving route unavailable; saved optimizer driving estimates are shown where available.' : 'Driving estimates may vary with traffic and local conditions. Transit times are not provided.'}</p></article>
      <article className="trip-budget-summary"><div className="eyebrow"><Wallet size={15} /> YOUR BUDGET</div><strong>{money(trip.final_trip?.budget, trip.final_trip?.currency)}</strong><p>Total approved trip budget</p><div><span>Activity cap</span><b>{money(trip.budget_allocation?.categories?.find(item => item.category === 'activities_attractions')?.allocated_amount, trip.final_trip?.currency)}</b></div><div><span>Known activity spend</span><b>{money(itinerary.priced_activity_cost, trip.final_trip?.currency)}</b></div><Link to={`/trips/${trip.trip_id}/budget`}>Review allocation <ArrowRight size={14} /></Link></article>
    </aside></div></main></SiteLayout>
}

function formatTripDate(start, offset) {
  if (!start) return `Day ${offset + 1}`
  const value = new Date(`${start}T12:00:00`)
  value.setDate(value.getDate() + offset)
  return value.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function TripMapPage() {
  const { trip, loading, error } = useTripRecord()
  const { session } = useAuth()
  const [activeDay, setActiveDay] = useState(null)
  if (loading) return <SiteLayout><LoadingScreen label="Opening your trip map" /></SiteLayout>
  if (error || !trip) return <SiteLayout><EmptyState title="This trip isn’t available" body={error || 'The trip could not be found for this account.'} action="View my trips" to="/my-trips" /></SiteLayout>
  const itinerary = trip.optimized_itinerary
  const days = itinerary?.days || []
  const selectedDay = activeDay ?? days[0]?.day_number
  const mapItinerary = itinerary ? { ...itinerary, days: days.filter(day => day.day_number === selectedDay) } : null
  return <SiteLayout><main className="page-main trip-workspace"><TripHero trip={trip} eyebrow="YOUR JOURNEY · PLACES AND ROUTES" title={<>Explore {trip.final_trip?.destination || 'your trip'} <em>on the map</em></>} />{days.length ? <div className="map-day-filter">{days.map(day => <button key={day.day_number} className={selectedDay === day.day_number ? 'active' : ''} onClick={() => setActiveDay(day.day_number)}>Day {day.day_number}<small>{formatTripDate(trip.final_trip?.departure_date, day.day_number - 1)}</small></button>)}</div> : null}<section className="map-page-card"><div className="map-page-heading"><div><div className="eyebrow"><MapPin size={15} /> RESOLVED TRIP STOPS</div><h2>{selectedDay ? `Day ${selectedDay} route` : 'Trip route'}</h2><p>Only geocoded stops from your saved itinerary appear here.</p></div><Link className="secondary-button" to={`/trips/${trip.trip_id}/itinerary`}>Back to itinerary <ArrowRight size={15} /></Link></div><TripMap activities={trip.activity_intelligence?.activities || []} itinerary={mapItinerary} accessToken={session?.access_token} /></section></main></SiteLayout>
}

function MyTripsPage() {
  const api = useVoyageApi()
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => { let cancelled = false; api('/api/trips').then(result => { if (!cancelled) setTrips(result.trips || []) }).catch(reason => { if (!cancelled) setError(reason.message) }).finally(() => { if (!cancelled) setLoading(false) }); return () => { cancelled = true } }, [api])
  return <SiteLayout><main className="page-main"><div className="page-intro compact"><div className="eyebrow"><span /> YOUR SAVED JOURNEYS</div><h1>My <em>trips</em></h1><p>Your planning checkpoints and finished itineraries, together in one place.</p><Link className="primary-button" to="/plan-trip">Plan a new journey <ArrowRight size={16} /></Link></div>
    {loading ? <LoadingScreen label="Loading your saved trips" /> : error ? <div className="form-error"><AlertCircle size={17} />{error}</div> : trips.length ? <div className="saved-trip-grid">{trips.map(trip => <article className="saved-trip-card" key={trip.trip_id}><DestinationImage destination={trip.destination}><span>{titleCase(trip.status)}</span></DestinationImage><div className="saved-trip-body"><h2>{trip.destination || 'Trip details in progress'}</h2><p>{trip.origin ? `${trip.origin} → ` : ''}{dates(trip.departure_date, trip.return_date)}</p><div><span><Users size={15} />{trip.travelers || '—'} travellers</span><span><Wallet size={15} />{money(trip.budget, trip.currency)}</span></div><Link className="text-link" to={`/trips/${trip.trip_id}/${trip.status === 'budget_review' ? 'budget' : trip.status === 'needs_clarification' ? 'clarification' : 'itinerary'}`}>{trip.status === 'budget_review' ? 'Continue budget review' : trip.status === 'needs_clarification' ? 'Add trip details' : 'Open trip'} <ArrowRight size={15} /></Link></div></article>)}</div> : <EmptyState title="Your next journey starts here" body="Plans you create will be saved to your account so you can return to the budget review or itinerary later." action="Plan a trip" to="/plan-trip" />}
  </main></SiteLayout>
}

function AuthPage({ mode = 'login' }) {
  const auth = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { recoveryMode } = auth
  const [newPassword, setNewPassword] = useState('')
  const isSignup = mode === 'signup'
  const isForgot = mode === 'forgot'

  async function submit(event) {
    event.preventDefault(); setError(''); setNotice(''); setBusy(true)
    try {
      if (recoveryMode) {
        await auth.updatePassword(newPassword)
        setNotice('Your password has been updated. You can continue planning securely.')
        auth.clearRecoveryMode()
      } else if (isForgot) {
        await auth.resetPassword(email)
        setNotice('If an account exists for that email, a password reset link is on its way.')
      } else if (isSignup) {
        const result = await auth.signUp(email, password)
        setNotice(result.session ? 'Your account is ready.' : 'Check your email to verify your account, then sign in.')
        if (result.session) navigate('/plan-trip')
      } else {
        await auth.signIn(email, password)
        navigate('/my-trips')
      }
    } catch (reason) { setError(reason.message || 'Authentication could not be completed.') }
    finally { setBusy(false) }
  }

  const title = recoveryMode ? 'Choose a new password' : isForgot ? 'Reset your password' : isSignup ? 'Create your account' : 'Welcome back'
  return <SiteLayout><main className="auth-page"><section className="auth-visual"><div className="auth-visual-shade" /><div><div className="eyebrow light"><span /> YOUR JOURNEY, YOURS</div><h1>Go further<br /><em>with a plan.</em></h1><p>Your trips, budgets and itineraries stay connected to your account.</p></div></section><section className="auth-form-wrap"><form className="auth-card" onSubmit={submit}><div className="eyebrow"><span /> VOYAGEAI ACCOUNT</div><h2>{title}</h2><p>{isSignup ? 'Save your plans and pick up right where you left off.' : isForgot ? 'We’ll email you a secure link to reset your password.' : 'Sign in to continue to your saved travel plans.'}</p>
      {!auth.configured && <div className="config-notice"><ShieldCheck size={17} /><span>Supabase Auth is not configured yet. Add the frontend project URL and publishable key to enable account access.</span></div>}
      {(!recoveryMode) && <label>Email address<input required type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" /></label>}
      {!isForgot && !recoveryMode && <label>Password<div className="password-field"><input required type={passwordVisible ? 'text' : 'password'} minLength={8} autoComplete={isSignup ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} placeholder={isSignup ? 'At least 8 characters' : 'Your password'} /><button type="button" aria-label={passwordVisible ? 'Hide password' : 'Show password'} onClick={() => setPasswordVisible(value => !value)}>{passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>}
      {recoveryMode && <label>New password<input required type="password" minLength={8} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>}
      {error && <div className="form-error"><AlertCircle size={16} />{error}</div>}{notice && <div className="success-notice"><CheckCircle2 size={16} />{notice}</div>}
      <button className="primary-button auth-submit" disabled={busy || (!auth.configured && !import.meta.env.DEV)}>{busy ? <LoaderCircle size={17} className="spin" /> : recoveryMode ? <KeyRound size={17} /> : <LockKeyhole size={17} />}{busy ? 'Please wait…' : recoveryMode ? 'Update password' : isForgot ? 'Send reset link' : isSignup ? 'Create account' : 'Sign in'}</button>
      <div className="auth-links">{mode === 'login' && <Link to="/forgot-password">Forgot password?</Link>}{mode === 'login' ? <span>New to VoyageAI? <Link to="/signup">Create an account</Link></span> : !isForgot && <span>Already have an account? <Link to="/login">Sign in</Link></span>}{isForgot && <span>Remembered it? <Link to="/login">Back to sign in</Link></span>}</div>
    </form></section></main></SiteLayout>
}

function AccountPage() {
  const { user, signOut, configured } = useAuth()
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  return <SiteLayout><main className="page-main account-page"><div className="page-intro compact"><div className="eyebrow"><span /> YOUR ACCOUNT</div><h1>Account <em>settings</em></h1></div>{user ? <section className="account-card"><span className="large-avatar">{user.email?.[0]?.toUpperCase()}</span><div><small>Signed in as</small><h2>{user.email}</h2><p>Trips and saved workflow checkpoints belong to this account.</p></div><button className="secondary-button" onClick={async () => { try { await signOut(); setNotice('You have signed out.') } catch (reason) { setError(reason.message) } }}><LogOut size={16} /> Sign out</button></section> : <section className="account-card"><ShieldCheck /><div><h2>{configured ? 'Sign in to view your account' : 'Auth setup required'}</h2><p>Set up Supabase Auth to enable secure user accounts and persistent trip ownership.</p></div><Link className="primary-button" to="/login">Sign in <ArrowRight size={15} /></Link></section>}{notice && <div className="success-notice">{notice}</div>}{error && <div className="form-error">{error}</div>}</main></SiteLayout>
}

function EmptyState({ title, body, action, to }) {
  return <section className="empty-state"><span><Compass size={23} /></span><h2>{title}</h2><p>{body}</p>{action && <Link className="primary-button" to={to}>{action} <ArrowRight size={16} /></Link>}</section>
}

function ProtectedPage({ children }) {
  return <PrivateRoute>{children}</PrivateRoute>
}

function App() {
  const [trip, setTrip] = useState(null)
  const tripValue = useMemo(() => ({ trip, setTrip }), [trip])
  return <AuthProvider><TripContext.Provider value={tripValue}><BrowserRouter><Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/plan-trip" element={<ProtectedPage><PlanTripPage /></ProtectedPage>} />
    <Route path="/trips/:tripId/budget" element={<ProtectedPage><BudgetReviewPage /></ProtectedPage>} />
    <Route path="/trips/:tripId/clarification" element={<ProtectedPage><TripClarificationPage /></ProtectedPage>} />
    <Route path="/trips/:tripId/itinerary" element={<ProtectedPage><ItineraryPage /></ProtectedPage>} />
    <Route path="/trips/:tripId/map" element={<ProtectedPage><TripMapPage /></ProtectedPage>} />
    <Route path="/my-trips" element={<ProtectedPage><MyTripsPage /></ProtectedPage>} />
    <Route path="/login" element={<AuthPage mode="login" />} />
    <Route path="/signup" element={<AuthPage mode="signup" />} />
    <Route path="/forgot-password" element={<AuthPage mode="forgot" />} />
    <Route path="/account" element={<ProtectedPage><AccountPage /></ProtectedPage>} />
    <Route path="*" element={<SiteLayout><EmptyState title="We couldn’t find that page" body="The link may have changed. Return home and continue planning from there." action="Back to VoyageAI" to="/" /></SiteLayout>} />
  </Routes></BrowserRouter></TripContext.Provider></AuthProvider>
}

export default App
