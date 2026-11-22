import { useMemo, useState } from 'react'
import { AlertCircle, ArrowRight, RotateCcw, Sparkles, Wallet } from 'lucide-react'
import './BudgetEditor.css'

const colors = ['#426f69', '#6f9385', '#c89d61', '#8b9980', '#738da0', '#c47a5e']
const money = (value, currency) => new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value || 0))
const categoryLabels = {
  transportation: 'Transportation', accommodation: 'Accommodation', food_dining: 'Food and dining',
  local_transportation: 'Local transportation', activities_attractions: 'Activities and attractions',
}
const rejectionLabels = {
  irrelevant_source: 'not specific to this destination or category', missing_amount: 'no usable amount was found',
  missing_currency: 'currency is missing', missing_cost_basis: 'the price unit is incomplete',
  ambiguous_currency: 'currency is ambiguous', ambiguous_cost_basis: 'the price unit is ambiguous',
  ambiguous_accommodation_unit: 'room, guest or capsule unit is unclear', illustrative_example: 'an illustrative example, not a trip price',
  tax_amount: 'a tax amount, not an accommodation rate', unspecified_attraction: 'the attraction is not identified',
  ambiguous_price: 'multiple or incomplete amounts could not be separated', unsupported_currency: 'currency is unsupported',
}
const shortQuote = value => {
  const normalized = (value || '').replace(/\s+/g, ' ').trim()
  return normalized.length > 240 ? `${normalized.slice(0, 237)}…` : normalized
}

function categoryReason(category, costResearch, options) {
  const matchingOptions = options.filter(item => item.estimate.category === category)
  if (matchingOptions.length) return `${matchingOptions.length} sourced option${matchingOptions.length === 1 ? '' : 's'} need your selection before they affect this category. Fare-class prices require the applicable traveller count; per-ride fares require a ride count.`
  const errors = costResearch?.search_errors?.[category]
  if (errors) return `Research for this category could not complete (${errors}). No price was assumed.`
  const statements = (costResearch?.price_statements || []).filter(item => item.category === category)
  const reasons = [...new Set(statements.flatMap(item => item.rejection_reasons || []))]
  if (reasons.length) return `No estimate was applied because ${reasons.slice(0, 2).map(reason => rejectionLabels[reason] || reason.replaceAll('_', ' ')).join(' and ')}.`
  if (category === 'local_transportation') return 'A fare without a ride count, or a pass that has not been selected, stays unallocated.'
  if (category === 'accommodation') return 'No room, guest or capsule nightly price with a clear unit was available. Accommodation remains unallocated.'
  return 'No source-backed price with a clear currency and unit was available. This category remains unallocated.'
}

export default function BudgetEditor({ allocation, costResearch, activities = [], loading, onConfirm, onRegenerate }) {
  const [amounts, setAmounts] = useState(() => Object.fromEntries(allocation.categories.map(item => [item.category, String(item.allocated_amount)])))
  const [error, setError] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [activityCosts, setActivityCosts] = useState({})
  const [evidenceChoices, setEvidenceChoices] = useState({})

  const options = costResearch?.options || []
  const optionsByCategory = options.reduce((groups, option) => {
    const category = option.estimate.category
    groups[category] ||= []
    groups[category].push(option)
    return groups
  }, {})
  const rejectedStatements = (costResearch?.price_statements || []).filter(item => !item.accepted)
  const rejectedSourcesWithoutStatements = (costResearch?.sources || []).filter(source => !source.price_statements?.length && source.rejection_reasons?.length)
  const rejectedCount = rejectedStatements.length + rejectedSourcesWithoutStatements.length

  const rows = allocation.categories
  const total = Number(allocation.total_budget)
  const values = rows.map(item => Number(amounts[item.category]))
  const enteredAll = rows.every(item => amounts[item.category] !== '' && Number.isFinite(Number(amounts[item.category])))
  const allocated = values.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0)
  const remaining = total - allocated
  const overBudget = allocated > total + 0.001
  const validationMessage = error || (overBudget ? `Your allocations exceed the total budget by ${money(allocated - total, allocation.currency)}.` : '')
  const percentUsed = total > 0 ? Math.max(0, Math.min(100, allocated / total * 100)) : 0
  const chartStyle = useMemo(() => {
    const chartRows = rows.map((row, index) => ({ value: Math.max(0, Number(amounts[row.category]) || 0), color: colors[index] }))
    chartRows.push({ value: Math.max(0, total - chartRows.reduce((sum, row) => sum + row.value, 0)), color: '#e6e9e5' })
    const sum = chartRows.reduce((value, row) => value + row.value, 0) || 1
    const stops = chartRows.reduce((result, row) => {
      const end = result.cursor + row.value / sum * 100
      return { cursor: end, parts: [...result.parts, `${row.color} ${result.cursor}% ${end}%`] }
    }, { cursor: 0, parts: [] }).parts
    return { background: `conic-gradient(${stops.join(', ')})` }
  }, [amounts, rows, total])

  function selectedEvidenceAmount(option, choice) {
    const estimate = option.estimate
    const travelers = choice.traveler_count ? Number(choice.traveler_count) : allocation.travelers
    const nights = Math.max(0, allocation.trip_days - 1)
    const multipliers = {
      per_trip: 1, per_traveler: travelers, per_admission: travelers,
      per_day: allocation.trip_days, per_night: nights,
      per_room_per_night: nights, per_capsule_per_night: travelers * nights,
      per_person_per_room_per_night: travelers * nights,
      per_traveler_per_day: travelers * allocation.trip_days,
      per_traveler_per_night: travelers * nights,
      per_ride: Number(choice.quantity || 0),
    }
    return Number(estimate.amount) * (multipliers[estimate.basis] ?? 1)
  }

  function applyEvidenceOptions() {
    const selected = options.filter(option => evidenceChoices[option.option_id]?.enabled)
    if (!selected.length) { setError('Select at least one compatible evidence option first.'); return }
    const groups = new Map()
    for (const option of selected) {
      const estimate = option.estimate
      if (estimate.currency !== allocation.currency) { setError('Selected evidence uses a different currency and cannot be applied without a verified conversion.'); return }
      const choice = evidenceChoices[option.option_id]
      if (estimate.fare_class && (!choice.traveler_count || Number(choice.traveler_count) < 1)) { setError(`Enter the number of ${estimate.fare_class} travellers for the selected pass.`); return }
      if (estimate.basis === 'per_ride' && (!choice.quantity || Number(choice.quantity) < 1)) { setError('Enter a ride count before applying a per-ride fare.'); return }
      const current = groups.get(estimate.category)
      if (current && current.group_id !== option.group_id) { setError('Choose one competing option per category.'); return }
      if (!current) groups.set(estimate.category, { group_id: option.group_id, value: 0, options: [] })
      const group = groups.get(estimate.category)
      if (estimate.fare_class && group.options.includes(estimate.fare_class)) { setError('Select only one option for each traveller type.'); return }
      if (estimate.fare_class) group.options.push(estimate.fare_class)
      group.value += selectedEvidenceAmount(option, choice)
    }
    setAmounts(current => {
      const next = { ...current }
      for (const [category, group] of groups) next[category] = String(Math.round(group.value * 100) / 100)
      return next
    })
    setError('')
  }

  function setCategory(category, value) {
    setAmounts(current => ({ ...current, [category]: value }))
    setError('')
  }

  async function confirm() {
    if (!enteredAll || values.some(value => value < 0)) {
      setError('Enter a valid non-negative amount for every category.')
      return
    }
    if (allocated > total + 0.001) {
      setError(`Your allocations exceed the total budget by ${money(allocated - total, allocation.currency)}.`)
      return
    }
    setError('')
    const enteredCosts = Object.fromEntries(Object.entries(activityCosts).filter(([, amount]) => amount !== '').map(([name, amount]) => [name, Number(amount)]))
    if (Object.values(enteredCosts).some(value => !Number.isFinite(value) || value < 0)) {
      setError('Enter valid non-negative costs for activities, or leave them blank.')
      return
    }
    try {
      const selections = options.filter(option => evidenceChoices[option.option_id]?.enabled).map(option => ({
        option_id: option.option_id,
        traveler_count: evidenceChoices[option.option_id].traveler_count ? Number(evidenceChoices[option.option_id].traveler_count) : null,
        quantity: evidenceChoices[option.option_id].quantity ? Number(evidenceChoices[option.option_id].quantity) : null,
      }))
      await onConfirm(Object.fromEntries(rows.map(row => [row.category, Number(amounts[row.category])])), enteredCosts, selections)
    } catch (reason) {
      setError(reason?.message || 'Could not confirm this budget. Review activity costs and try again.')
    }
  }

  async function regenerate() {
    setBusyAction('regenerate')
    setError('')
    try { await onRegenerate() }
    catch (reason) { setError(reason.message || 'Could not regenerate the allocation.') }
    finally { setBusyAction('') }
  }

  function reset() {
    setAmounts(Object.fromEntries(rows.map(row => [row.category, String(row.allocated_amount)])))
    setError('')
  }

  return <section className="budget-editor" aria-labelledby="budget-editor-title">
    <div className="budget-editor-heading">
      <div>
        <div className="budget-editor-kicker"><Wallet size={15} /> BEFORE WE BUILD YOUR DAYS</div>
        <h2 id="budget-editor-title">Review your trip budget</h2>
        <p>Set a cap for each category. Unassigned funds stay unallocated; changing one amount never adjusts another.</p>
      </div>
      <div className="budget-total-chip"><span>Total trip budget</span><strong>{money(total, allocation.currency)}</strong><small>{allocation.travelers} travellers · {allocation.trip_days} days</small></div>
    </div>

    {allocation.allocation_note && <div className="budget-evidence-note"><Sparkles size={16} /><span>{allocation.allocation_note}</span></div>}

    {options.length > 0 && <details className="budget-research-section" aria-label="Selectable sourced cost evidence">
      <summary>Available cost evidence <span>{options.length} option{options.length === 1 ? '' : 's'}</span></summary>
      <p>Select an option to use its source-backed estimate. These are estimates, not confirmed bookings; nothing is applied until you select it.</p>
      {Object.entries(optionsByCategory).map(([category, categoryOptions]) => <section className="budget-option-category" key={category}>
        <h3>{categoryLabels[category] || category.replaceAll('_', ' ')}</h3>
        {categoryOptions.map(option => {
          const estimate = option.estimate
          const choice = evidenceChoices[option.option_id] || {}
          const incompatible = estimate.currency !== allocation.currency
          return <article className="known-cost-note cost-option-card" key={option.option_id}>
            <label className="cost-option-choice"><input type="checkbox" checked={Boolean(choice.enabled)} disabled={incompatible} onChange={event => setEvidenceChoices(current => ({ ...current, [option.option_id]: { ...current[option.option_id], enabled: event.target.checked } }))} /> <strong>{option.label}</strong></label>
            <p><strong>{money(estimate.amount_min ?? estimate.amount, estimate.currency)} to {money(estimate.amount_max ?? estimate.amount, estimate.currency)}</strong> | {estimate.basis.replaceAll('_', ' ')}{estimate.fare_class ? ` | ${estimate.fare_class}-only fare` : ''} | {estimate.certainty === 'confirmed' ? 'confirmed source price' : 'indicative estimate'} | {estimate.confidence_level || 'low'} confidence | retrieved {estimate.retrieved_on || 'date unavailable'}</p>
            {estimate.evidence_quote && <blockquote>{shortQuote(estimate.evidence_quote)}</blockquote>}
            <p>{estimate.source_type === 'official' ? 'Official source' : estimate.source_type === 'third_party' ? 'Third-party source' : 'Source type unverified'}{estimate.source_url && <> | <a href={estimate.source_url} target="_blank" rel="noreferrer">View source: {estimate.source}</a></>}{estimate.taxes_included === true ? ' | taxes included' : estimate.taxes_included === false ? ' | taxes excluded' : ''}</p>
            {incompatible && <p className="cost-incompatible">This {estimate.currency} evidence cannot enter your {allocation.currency} budget without a verified conversion.</p>}
            {estimate.fare_class && choice.enabled && <label className="cost-option-quantity">Number of {estimate.fare_class} travellers <input type="number" min="1" max={allocation.travelers} value={choice.traveler_count || ''} onChange={event => setEvidenceChoices(current => ({ ...current, [option.option_id]: { ...current[option.option_id], traveler_count: event.target.value } }))} /></label>}
            {estimate.basis === 'per_ride' && choice.enabled && <label className="cost-option-quantity">Ride count <input type="number" min="1" value={choice.quantity || ''} onChange={event => setEvidenceChoices(current => ({ ...current, [option.option_id]: { ...current[option.option_id], quantity: event.target.value } }))} /></label>}
            {choice.enabled && <p className="cost-calculation">Calculated for this trip: {money(selectedEvidenceAmount(option, choice), estimate.currency)}</p>}
          </article>
        })}
      </section>)}
      <button type="button" className="budget-reset-button" onClick={applyEvidenceOptions}>Apply selected evidence to category amounts</button>
    </details>}

    <div className="budget-editor-layout">
      <div className="budget-category-grid">
        {rows.map((row, index) => <article className="budget-category-card" key={row.category} style={{ '--category-color': colors[index] }}>
          <div className="budget-category-title"><span className="budget-category-dot" /><h3>{row.label}</h3></div>
          <label className="budget-amount-label" htmlFor={`allocation-${row.category}`}>Your allocation</label>
          <div className="budget-amount-input"><span>{allocation.currency}</span><input id={`allocation-${row.category}`} type="number" min="0" step="0.01" inputMode="decimal" value={amounts[row.category] ?? ''} onChange={event => setCategory(row.category, event.target.value)} aria-label={`${row.label} allocation`} /></div>
          <div className="budget-category-meta"><span>{total ? `${((Number(amounts[row.category]) || 0) / total * 100).toFixed(1)}% of total` : '0% of total'}</span><span className={`cost-certainty ${row.certainty}`}>{row.certainty === 'unavailable' ? (row.cost_evidence?.length ? 'Other currency evidence' : 'No sourced cost') : `${row.certainty} cost`}</span></div>
          {row.known_cost_estimate != null && <p className="budget-known-estimate">Indicative sourced cost for this trip: {money(row.known_cost_estimate_min ?? row.known_cost_estimate, allocation.currency)} to {money(row.known_cost_estimate, allocation.currency)}</p>}
          {row.cost_evidence?.length > 0 ? <details className="budget-category-evidence"><summary>View {row.cost_evidence.length} source record{row.cost_evidence.length === 1 ? '' : 's'}</summary>{row.cost_evidence.map((evidence, i) => <p key={`${evidence.source_url}-${i}`}>{money(evidence.amount_min ?? evidence.amount, evidence.currency)} to {money(evidence.amount, evidence.currency)} ? {evidence.basis.replaceAll('_', ' ')} | {evidence.certainty === 'confirmed' ? 'confirmed source price' : 'indicative'} | {evidence.confidence_level || 'low'} confidence ? {evidence.retrieved_on || 'date unavailable'} | {evidence.source_url ? <a href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.source}</a> : evidence.source}{evidence.currency !== allocation.currency && ' (different currency; excluded from allocation)'}</p>)}</details>
            : row.category !== 'contingency' && <p className="budget-category-explanation">{categoryReason(row.category, costResearch, options)}</p>}
        </article>)}
      </div>

      <div className="budget-activity-costs">
        <h3>Attraction costs</h3>
        <p>Unknown admission prices remain unallocated and are never treated as free. You can enter a manual estimate for budget-aware scheduling, or continue with a provisional itinerary that clearly marks activities needing price verification.</p>
        {activities.filter(activity => activity.admission_status === 'priced' && activity.cost_status === 'indicative').map(activity => <p key={activity.name}>{activity.name}: indicative {money(activity.estimated_cost, activity.currency || allocation.currency)} per {activity.cost_basis === 'per_group' ? 'group' : 'traveller'} · {activity.cost_source_type === 'official' ? 'official source' : 'third-party source'} · {activity.cost_confidence_level || 'low'} confidence{activity.cost_source_url && <> · <a href={activity.cost_source_url} target="_blank" rel="noreferrer">source</a></>}</p>)}
        {activities.filter(activity => activity.admission_status === 'verified_free').map(activity => <p key={activity.name}>{activity.name}: verified free admission · official evidence: “{activity.cost_evidence}”{activity.cost_source_url && <> · <a href={activity.cost_source_url} target="_blank" rel="noreferrer">source</a></>}</p>)}
        {activities.filter(activity => activity.admission_status === 'unpriced').map(activity => <label key={activity.name} className="activity-cost-entry">{activity.name} · admission price unknown<span><input type="number" min="0" step="0.01" placeholder="Optional cost per traveller" value={activityCosts[activity.name] ?? ''} onChange={event => setActivityCosts(current => ({ ...current, [activity.name]: event.target.value }))} /> {allocation.currency}</span></label>)}
        {costResearch?.estimates?.filter(estimate => estimate.category === 'activities_attractions' && !activities.some(activity => activity.cost_source_url === estimate.source_url)).map((estimate, index) => <p key={`${estimate.source_url}-${index}`}>Unmatched or other-currency admission evidence: {money(estimate.amount_min ?? estimate.amount, estimate.currency)}–{money(estimate.amount, estimate.currency)} {estimate.basis.replaceAll('_', ' ')} · {estimate.confidence_level || 'low'} confidence · <a href={estimate.source_url} target="_blank" rel="noreferrer">{estimate.source}</a>{estimate.currency !== allocation.currency && ' (different currency; enter a trip-currency estimate manually if you want to use it)'}</p>)}
        {costResearch?.note && <small>{costResearch.note}</small>}

      </div>

      {rejectedCount > 0 && <details className="budget-diagnostics">
        <summary>Rejected research <span>{rejectedCount} item{rejectedCount === 1 ? '' : 's'}</span></summary>
        <p>These statements were not used to allocate your budget. Rejection reasons are shown with each source.</p>
        {[...new Set([...rejectedStatements.map(item => item.category), ...rejectedSourcesWithoutStatements.map(item => item.category)])].map(category => <section className="budget-diagnostic-category" key={category}>
          <h3>{categoryLabels[category] || category.replaceAll('_', ' ')}</h3>
          {rejectedStatements.filter(item => item.category === category).map((statement, index) => <article key={`${statement.source_url}-${index}`}>
            <strong>{shortQuote(statement.description || statement.evidence_quote)}</strong>
            <p>{(statement.rejection_reasons || []).map(reason => rejectionLabels[reason] || reason.replaceAll('_', ' ')).join('; ')}</p>
            {statement.source_url && <a href={statement.source_url} target="_blank" rel="noreferrer">{statement.source_title || 'Open source'}</a>}
          </article>)}
          {rejectedSourcesWithoutStatements.filter(source => source.category === category).map((source, index) => <article key={`${source.url}-${index}`}>
            <strong>{source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a> : source.title}</strong>
            <p>{source.rejection_reasons.map(reason => rejectionLabels[reason] || reason.replaceAll('_', ' ')).join('; ')}</p>
          </article>)}
        </section>)}
      </details>}

      <aside className="budget-summary-card">
        <div className="budget-chart" style={chartStyle} role="img" aria-label="Budget allocation distribution chart"><div><small>Allocated</small><strong>{money(allocated, allocation.currency)}</strong></div></div>
        <div className="budget-chart-legend">{rows.map((row, index) => <span key={row.category}><i style={{ background: colors[index] }} />{row.label}</span>)}<span><i style={{ background: '#e6e9e5' }} />Unallocated</span></div>
        <div className="budget-utilization"><div><span>Budget utilization</span><strong>{percentUsed.toFixed(1)}%</strong></div><div className="budget-utilization-track"><i style={{ width: `${percentUsed}%` }} /></div></div>
        <div className={`budget-remaining ${remaining < -0.001 ? 'over' : ''}`}><span>{remaining < 0 ? 'Over budget' : 'Remaining / unallocated'}</span><strong>{money(Math.abs(remaining), allocation.currency)}</strong></div>
        {validationMessage && <p className="budget-validation" role="alert"><AlertCircle size={15} />{validationMessage}</p>}
        <div className="budget-editor-actions"><button type="button" className="budget-reset-button" onClick={reset} disabled={loading}><RotateCcw size={14} />Reset to AI recommendation</button><button type="button" className="budget-reset-button" onClick={regenerate} disabled={loading || busyAction !== ''}><Sparkles size={14} />{busyAction === 'regenerate' ? 'Regenerating…' : 'Regenerate allocation'}</button></div>
        <button type="button" className="budget-confirm-button" onClick={confirm} disabled={loading}>{loading ? 'Building itinerary…' : <>Confirm allocation and build itinerary <ArrowRight size={16} /></>}</button>
      </aside>
    </div>
  </section>
}
