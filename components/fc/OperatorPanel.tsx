'use client';
import { useEffect, useState } from 'react';

export function OperatorPanel() {
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    try { setToken(sessionStorage.getItem('fc-lock-operator-token') || ''); } catch { /* Report storage failures on submit. */ }
  }, []);
  async function connect(event: React.FormEvent) {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) { setMessage('Masukkan token operator.'); return; }
    setBusy(true);
    try {
      const response = await fetch('/api/fc/locks', { headers: { Authorization: `Bearer ${candidate}` }, cache: 'no-store' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'Operator tidak dapat dihubungkan.');
      sessionStorage.setItem('fc-lock-operator-token', candidate);
      setMessage('Operator terhubung untuk sesi tab ini. Lock pick dan settlement siap digunakan.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Koneksi operator gagal.'); }
    finally { setBusy(false); }
  }
  function disconnect() {
    try { sessionStorage.removeItem('fc-lock-operator-token'); setToken(''); setMessage('Operator diputuskan.'); }
    catch { setMessage('Penyimpanan sesi tidak tersedia.'); }
  }
  return <section className="card card-sm" style={{ marginBottom: '1rem' }} aria-label="Pengaturan operator">
    <strong>Operator settlement</strong>
    <form className="watchlist-token" onSubmit={connect}>
      <label htmlFor="fc-lock-token">Token operator</label>
      <div><input id="fc-lock-token" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} />
        <button disabled={busy} type="submit">{busy ? 'Memeriksa…' : 'Hubungkan'}</button>
        <button disabled={busy} type="button" onClick={disconnect}>Putuskan</button></div>
    </form><p role="status">{message}</p>
  </section>;
}
