import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function SynonymManager() {
  const [synonyms, setSynonyms] = useState([]);
  const [keyword, setKeyword] = useState('');
  const [synonym, setSynonym] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchSynonyms = async () => {
    try {
      const res = await axios.get("http://localhost:8000/synonyms_from_db");
      setSynonyms(res.data);
    } catch (e) {
      console.error(e);
      setError("Не удалось загрузить синонимы");
    }
  };

  const addSynonym = async () => {
    if (!keyword.trim() || !synonym.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await axios.post("http://localhost:8000/synonyms", null, {
        params: { keyword, synonym }
      });
      setKeyword("");
      setSynonym("");
      await fetchSynonyms();
    } catch (e) {
      console.error(e);
      setError("Не удалось добавить синоним");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSynonyms();
  }, []);

  // Группируем в виде { keyword: [syn1, syn2, ...], ... }
  const grouped = synonyms.reduce((acc, cur) => {
    acc[cur.keyword] = [...(acc[cur.keyword] || []), cur.synonym];
    return acc;
  }, {});

  return (
    <div>
      <h2>🔁 Синонимы</h2>

      {error && <div style={{ color: 'red' }}>{error}</div>}

      <div style={{ marginBottom: 12 }}>
        <input
          placeholder="Ключевое слово"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          disabled={loading}
        />
        <input
          placeholder="Синоним"
          value={synonym}
          onChange={e => setSynonym(e.target.value)}
          disabled={loading}
        />
        <button
          onClick={addSynonym}
          disabled={loading || !keyword.trim() || !synonym.trim()}
        >
          {loading ? 'Добавляю…' : 'Добавить'}
        </button>
      </div>

      <h3>Текущие синонимы</h3>
      <ul>
        {Object.entries(grouped).map(([key, values]) => (
          <li key={key}>
            <b>{key}</b> → {values.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}
