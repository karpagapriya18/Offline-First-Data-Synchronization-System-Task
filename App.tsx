import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { openDB } from 'idb'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './App.css'

type View = 'dashboard' | 'records' | 'history' | 'conflicts' | 'audit' | 'profile'

type RecordItem = {
  id?: number
  client_id: string
  title: string
  content?: string
  version: number
  is_deleted: boolean
  updated_at: string
  created_at?: string
  user_id?: number
  sync_status: 'local' | 'synced' | 'failed' | 'conflict'
}

type ChangeItem = {
  operation_id: string
  client_id: string
  operation: 'create' | 'update' | 'delete'
  title?: string
  content?: string
  version: number
  updated_at: string
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function db() {
  return openDB('offline-sync', 1, {
    upgrade(database) {
      database.createObjectStore('records', { keyPath: 'client_id' })
      database.createObjectStore('queue', { keyPath: 'operation_id' })
      database.createObjectStore('conflicts', { keyPath: 'id' })
      database.createObjectStore('history', { keyPath: 'id', autoIncrement: true })
    },
  })
}

function newId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`
}

function FeatureCard({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="feature-card">
      <span className="feature-icon">{icon}</span>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  )
}

function AuthScreen({
  mode,
  setMode,
  email,
  setEmail,
  password,
  setPassword,
  name,
  setName,
  submit,
  message,
}: {
  mode: 'login' | 'register'
  setMode: (mode: 'login' | 'register') => void
  email: string
  setEmail: (value: string) => void
  password: string
  setPassword: (value: string) => void
  name: string
  setName: (value: string) => void
  submit: () => void
  message: string
}) {
  const isRegister = mode === 'register'
  return (
    <main className="auth-page">
      <section className="auth-copy">
        <div className="brand-pill"><span>sync</span> Offline Sync System</div>
        <h1>{isRegister ? 'Save changes offline.' : 'Work online or offline.'}<span>{isRegister ? 'Sync without duplicates.' : 'Reconnect and synchronize.'}</span></h1>
        <p>
          {isRegister
            ? 'Create an account to manage records locally, queue every operation, and send changes safely when the network returns.'
            : 'Continue creating, updating, and deleting records even when the internet is unavailable. Pending changes stay in your local queue until sync is possible.'}
        </p>
        <div className="feature-grid">
          <FeatureCard icon="queue" title="Pending Queue" text="Offline operations are stored locally until connectivity is restored." />
          <FeatureCard icon="safe" title="Safe Sync" text="Duplicate requests are ignored and sync history is preserved." />
          <FeatureCard icon="lock" title="Secure Access" text="JWT authentication protects user data and profile actions." />
          <FeatureCard icon="local" title="Local Storage" text="IndexedDB keeps records available inside the browser." />
        </div>
      </section>

      <section className="auth-card">
        <h2>{isRegister ? 'Create account' : 'Welcome back'}</h2>
        <p>{isRegister ? 'Start using the offline-first synchronization workspace.' : 'Sign in to manage records and monitor synchronization status.'}</p>
        {isRegister && (
          <label>
            Username
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Username" />
          </label>
        )}
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="demo@example.com" />
        </label>
        <label>
          Password
          <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="password123" type="password" />
        </label>
        <button className="primary-auth" onClick={submit}>{isRegister ? 'Create Workspace' : 'Sign In'}</button>
        {message && <div className="auth-message">{message}</div>}
        <button className="link-button" onClick={() => setMode(isRegister ? 'login' : 'register')}>
          {isRegister ? 'Already registered? Sign in' : 'Need a workspace? Create account'}
        </button>
      </section>
    </main>
  )
}

function AppShell() {
  const [token, setToken] = useState(localStorage.getItem('token') || '')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [view, setView] = useState<View>('dashboard')
  const [email, setEmail] = useState('demo@example.com')
  const [password, setPassword] = useState('password123')
  const [name, setName] = useState('Demo User')
  const [records, setRecords] = useState<RecordItem[]>([])
  const [queue, setQueue] = useState<ChangeItem[]>([])
  const [conflicts, setConflicts] = useState<any[]>([])
  const [history, setHistory] = useState<any[]>([])
  const getNetworkStatus = () => navigator.onLine
  const [online, setOnline] = useState(getNetworkStatus())
  const [manualOffline, setManualOffline] = useState(false)
  const [message, setMessage] = useState('')
  const [search, setSearch] = useState('')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const api = useMemo(() => axios.create({
    baseURL: API_URL,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }), [token])
  const effectiveOnline = online && !manualOffline

  async function refreshLocal() {
    const database = await db()
    let storedRecords = await database.getAll('records') as RecordItem[]
    let storedQueue = await database.getAll('queue') as ChangeItem[]
    let storedConflicts = await database.getAll('conflicts') as any[]
    let storedHistory = await database.getAll('history') as any[]

    const hasDemoData =
      storedRecords.some((record) => record.client_id === 'demo-rec-001') &&
      storedQueue.some((change) => change.operation_id === 'demo-op-101') &&
      storedConflicts.some((conflict) => conflict.id === 9001) &&
      storedHistory.some((entry) => entry.sync_id === 'demo-sync-001')

    if (!hasDemoData) {
      await seedDemoData(true, false)
      storedRecords = await database.getAll('records') as RecordItem[]
      storedQueue = await database.getAll('queue') as ChangeItem[]
      storedConflicts = await database.getAll('conflicts') as any[]
      storedHistory = await database.getAll('history') as any[]
    }

    setRecords(storedRecords)
    setQueue(storedQueue)
    setConflicts(storedConflicts)
    setHistory(storedHistory)
  }

  async function seedDemoData(force = true, refreshAfter = true) {
    const database = await db()
    const existingRecords = await database.getAll('records')
    const existingQueue = await database.getAll('queue')
    const existingConflicts = await database.getAll('conflicts')
    const existingHistory = await database.getAll('history')

    const demoAlreadyLoaded =
      existingRecords.some((record) => record.client_id === 'demo-rec-001') &&
      existingQueue.some((change) => change.operation_id === 'demo-op-101') &&
      existingConflicts.some((conflict) => conflict.id === 9001) &&
      existingHistory.some((entry) => entry.sync_id === 'demo-sync-001')

    if (!force && demoAlreadyLoaded) {
      if (refreshAfter) await refreshLocal()
      return
    }

    const now = new Date()
    const minutesAgo = (minutes: number) => new Date(now.getTime() - minutes * 60000).toISOString()
    const sampleRecords: RecordItem[] = [
      { id: 1, client_id: 'demo-rec-001', title: 'Customer Visit Notes', content: 'Synced field visit summary with contact details and next action.', version: 3, is_deleted: false, user_id: 1, created_at: minutesAgo(240), updated_at: minutesAgo(180), sync_status: 'synced' },
      { id: 2, client_id: 'demo-rec-002', title: 'Inventory Count', content: 'Synced warehouse stock count for morning batch.', version: 2, is_deleted: false, user_id: 1, created_at: minutesAgo(220), updated_at: minutesAgo(160), sync_status: 'synced' },
      { client_id: 'demo-rec-003', title: 'Offline Expense Draft', content: 'Created while offline. Waiting for upload.', version: 0, is_deleted: false, user_id: 1, created_at: minutesAgo(45), updated_at: minutesAgo(45), sync_status: 'local' },
      { id: 4, client_id: 'demo-rec-004', title: 'Route Plan Update', content: 'Local update pending because offline mode was enabled.', version: 1, is_deleted: false, user_id: 1, created_at: minutesAgo(140), updated_at: minutesAgo(25), sync_status: 'local' },
      { id: 5, client_id: 'demo-rec-005', title: 'Pricing Sheet Conflict', content: 'Client changed discount while server changed approval state.', version: 2, is_deleted: false, user_id: 1, created_at: minutesAgo(300), updated_at: minutesAgo(18), sync_status: 'conflict' },
    ]

    const sampleQueue: ChangeItem[] = [
      { operation_id: 'demo-op-101', client_id: 'demo-rec-003', operation: 'create', title: 'Offline Expense Draft', content: 'Created while offline. Waiting for upload.', version: 0, updated_at: minutesAgo(45) },
      { operation_id: 'demo-op-102', client_id: 'demo-rec-004', operation: 'update', title: 'Route Plan Update', content: 'Local update pending because offline mode was enabled.', version: 1, updated_at: minutesAgo(25) },
    ]

    await Promise.all(sampleRecords.map((record) => database.put('records', record)))
    await Promise.all(sampleQueue.map((change) => database.put('queue', change)))
    await database.put('conflicts', {
      id: 9001,
      sync_id: 'demo-sync-conflict',
      operation_id: 'demo-op-103',
      client_id: 'demo-rec-005',
      status: 'open',
      strategy: 'manual',
      server_version: 3,
      client_version: 2,
      server_payload: { title: 'Pricing Sheet Conflict', content: 'Server approved 8 percent discount.', version: 3 },
      client_payload: { title: 'Pricing Sheet Conflict', content: 'Client requested 12 percent discount offline.', version: 2 },
      created_at: minutesAgo(15),
    })
    await database.put('history', { id: 7001, sync_id: 'demo-sync-001', message: 'Synchronization completed', synced: 2, conflicts: 0, failed: 0, duplicates: 0, created_at: minutesAgo(120), results: [{ operation_id: 'demo-history-001', client_id: 'demo-rec-001', status: 'synced' }, { operation_id: 'demo-history-002', client_id: 'demo-rec-002', status: 'synced' }] })
    await database.put('history', { id: 7002, sync_id: 'demo-sync-002', message: 'Synchronization completed with conflict', synced: 1, conflicts: 1, failed: 0, duplicates: 0, created_at: minutesAgo(16), results: [{ operation_id: 'demo-op-103', client_id: 'demo-rec-005', status: 'conflict', error: 'Version mismatch detected.' }] })

    setMessage('Sample records, pending sync items, synced operations, and conflicts were loaded.')
    if (refreshAfter) await refreshLocal()
  }

  async function authenticate() {
    try {
      if (authMode === 'register') {
        await api.post('/auth/register', { name, email, password })
      }
      const result = await axios.post(`${API_URL}/auth/login`, { email, password })
      localStorage.setItem('token', result.data.access_token)
      setToken(result.data.access_token)
      setMessage(authMode === 'register' ? 'Account created and signed in.' : 'Signed in successfully.')
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || 'Authentication failed.')
    }
  }

  function logout() {
    localStorage.removeItem('token')
    setToken('')
    setView('dashboard')
  }

  async function addRecord() {
    if (!title.trim()) return
    const item: RecordItem = {
      client_id: newId('record'),
      title,
      content,
      version: 0,
      is_deleted: false,
      updated_at: new Date().toISOString(),
      sync_status: 'local',
    }
    const change: ChangeItem = {
      operation_id: newId('op'),
      client_id: item.client_id,
      operation: 'create',
      title,
      content,
      version: 0,
      updated_at: item.updated_at,
    }
    const database = await db()
    await database.put('records', item)
    await database.put('queue', change)
    setTitle('')
    setContent('')
    await refreshLocal()
    if (effectiveOnline && token) await syncNow()
  }

  async function markDeleted(item: RecordItem) {
    const updated = { ...item, is_deleted: true, sync_status: 'local' as const, updated_at: new Date().toISOString() }
    const change: ChangeItem = {
      operation_id: newId('op'),
      client_id: item.client_id,
      operation: 'delete',
      version: item.version,
      updated_at: updated.updated_at,
    }
    const database = await db()
    await database.put('records', updated)
    await database.put('queue', change)
    await refreshLocal()
  }

  async function syncNow() {
    if (!token || !effectiveOnline) {
      setMessage('Offline mode is active. Changes are saved locally and will sync when you go online.')
      return
    }
    const database = await db()
    const changes = await database.getAll('queue') as ChangeItem[]
    if (!changes.length) {
      setMessage('No pending changes to synchronize.')
      return
    }
    try {
      const response = await api.post('/sync/synchronize', { changes, strategy: 'manual' })
      for (const result of response.data.results) {
        if (result.status === 'synced' && result.record) {
          await database.put('records', { ...result.record, sync_status: 'synced' })
          await database.delete('queue', result.operation_id)
        }
        if (result.status === 'duplicate') await database.delete('queue', result.operation_id)
        if (result.status === 'conflict' && result.conflict) await database.put('conflicts', result.conflict)
      }
      await database.add('history', { ...response.data, created_at: new Date().toISOString() })
      setMessage(`Sync complete: ${response.data.synced} synced, ${response.data.conflicts} conflicts, ${response.data.failed} failed.`)
      await refreshLocal()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || 'Synchronization failed.')
    }
  }

  useEffect(() => {
    refreshLocal()
    const onOnline = () => {
      setOnline(getNetworkStatus())
      if (!manualOffline) syncNow()
    }
    const onOffline = () => setOnline(false)
    const checkNetwork = () => setOnline(getNetworkStatus())
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    const interval = window.setInterval(checkNetwork, 1500)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      window.clearInterval(interval)
    }
  }, [token, manualOffline])

  if (!token) {
    return (
      <AuthScreen
        mode={authMode}
        setMode={setAuthMode}
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        name={name}
        setName={setName}
        submit={authenticate}
        message={message}
      />
    )
  }

  const visibleRecords = records.filter((record) => `${record.title} ${record.content || ''}`.toLowerCase().includes(search.toLowerCase()))
  const syncedCount = records.filter((record) => record.sync_status === 'synced').length

  const navItems: { key: View; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { key: 'records', label: 'Records', icon: 'list' },
    { key: 'history', label: 'Sync History', icon: 'clock' },
    { key: 'conflicts', label: 'Conflicts', icon: 'warn' },
    { key: 'audit', label: 'Audit Logs', icon: 'log' },
    { key: 'profile', label: 'Profile', icon: 'user' },
  ]

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="side-brand">
          <span className="brand-mark">sync</span>
          <div><strong>Offline Sync</strong><small>Data Platform</small></div>
        </div>
        <nav>
          {navItems.map((item) => (
            <button key={item.key} className={view === item.key ? 'active' : ''} onClick={() => setView(item.key)}>
              <span>{item.icon}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="side-status">
          <strong>{effectiveOnline ? 'Online' : 'Offline'}</strong>
          <small>{effectiveOnline ? 'Sync is available' : 'Local mode active'}</small>
        </div>
        <button className="logout" onClick={logout}>Logout</button>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div className="top-title"><span className="top-icon">grid</span><div><h2>Offline Sync System</h2><p>{view.replace('-', ' ')}</p></div></div>
          <div className="top-actions">
            <span className="online-pill">{effectiveOnline ? 'Online' : 'Offline'}</span>
            <button onClick={() => setManualOffline((value) => !value)}>
              {manualOffline ? 'Go Online' : 'Go Offline'}
            </button>
            <button onClick={logout}>Logout</button>
          </div>
        </header>
        {message && <div className="toast">{message}</div>}

        {view === 'dashboard' && (
          <section className="screen">
            <div className="screen-heading"><h1>Dashboard</h1><p>Monitor your records and synchronization status.</p></div>
            <div className="stat-grid">
              <div className="stat purple"><span>Total Records</span><strong>{records.length}</strong><em>records</em></div>
              <div className="stat orange"><span>Pending Sync</span><strong>{queue.length}</strong><em>queue</em></div>
              <div className="stat green"><span>Synced Operations</span><strong>{history.reduce((total, entry) => total + (entry.synced || 0), syncedCount)}</strong><em>done</em></div>
              <div className="stat red"><span>Conflicts</span><strong>{conflicts.length}</strong><em>alerts</em></div>
            </div>
            <div className="dashboard-grid">
              <div className="wide-card accent-purple">
                <h2>Synchronization</h2>
                <p>Current sync activity</p>
                <dl><dt>Total Operations</dt><dd>{history.length}</dd><dt>Pending</dt><dd>{queue.length}</dd><dt>Failed</dt><dd>0</dd></dl>
              </div>
              <div className="wide-card accent-blue">
                <h2>Quick Actions</h2>
                <p>Navigate to key areas</p>
                <div className="quick-actions">
                  <button onClick={() => setView('records')}>Records</button>
                  <button onClick={() => setView('history')}>Sync History</button>
                  <button className="danger-soft" onClick={() => setView('conflicts')}>Conflicts</button>
                  <button className="primary-soft" onClick={syncNow}>Refresh</button>
                  <button onClick={() => seedDemoData(true)}>Add Demo Data</button>
                </div>
              </div>
            </div>
          </section>
        )}

        {view === 'records' && (
          <section className="screen">
            <div className="screen-heading"><h1>Records</h1><p>Create, edit and manage your records locally with automatic synchronization.</p></div>
            <div className="mini-stats">
              <div><small>Connection</small><strong>{effectiveOnline ? 'Online' : 'Offline'}</strong></div>
              <div><small>Sync Queue</small><strong>{queue.length}</strong></div>
              <div><small>Storage</small><strong>IndexedDB</strong></div>
            </div>
            <div className="form-card">
              <small>New Record</small>
              <h2>Create Record</h2>
              <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Enter record title" /></label>
              <label>Description<textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Enter record description" /></label>
              <button className="primary-small" onClick={addRecord}>Create Record</button>
            </div>
            <div className="records-header"><div><h2>Local Records</h2><p>Records currently available in local storage.</p></div><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search records" /></div>
            <div className="record-grid">
              {visibleRecords.map((record, index) => (
                <article className="record-card" key={record.client_id}>
                  <span className="version">v{record.version}</span>
                  <h3>{record.title}</h3>
                  <small>Local ID #{index + 1}</small>
                  <p>{record.content || 'No description'}</p>
                  <div className="record-meta"><span>User ID<br /><b>{record.user_id || 1}</b></span><span>Version<br /><b>{record.version}</b></span></div>
                  <div className="record-actions"><button>Edit</button><button onClick={() => markDeleted(record)}>Delete</button></div>
                </article>
              ))}
            </div>
          </section>
        )}

        {view === 'history' && <JsonScreen title="Sync History" subtitle="Review previous synchronization batches." data={history} />}
        {view === 'conflicts' && <JsonScreen title="Conflicts" subtitle="Records requiring manual resolution." data={conflicts} />}
        {view === 'audit' && <JsonScreen title="Audit Logs" subtitle="Local activity and sync responses." data={[...history].reverse()} />}
        {view === 'profile' && <JsonScreen title="Profile" subtitle="Current local account session." data={{ email, online: effectiveOnline, manualOffline, records: records.length, pending: queue.length }} />}
      </section>
    </main>
  )
}

function JsonScreen({ title, subtitle, data }: { title: string; subtitle: string; data: any }) {
  return (
    <section className="screen">
      <div className="screen-heading"><h1>{title}</h1><p>{subtitle}</p></div>
      <pre className="json-panel">{JSON.stringify(data, null, 2)}</pre>
    </section>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<AppShell />} />
      </Routes>
    </BrowserRouter>
  )
}
