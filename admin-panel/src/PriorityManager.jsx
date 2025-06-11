import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function PriorityManager() {
  const [priorities, setPriorities] = useState([]);
  const [keyword, setKeyword] = useState('');
  const [docname, setDocname] = useState('');

  const fetch = async () => {
    const res = await axios.get("http://localhost:8000/priorities");
    setPriorities(res.data);
  };

  const add = async () => {
    await axios.post("http://localhost:8000/priorities", null, {
      params: { keyword, document_name: docname }
    });
    fetch();
  };

  const remove = async (id) => {
    try {
      await axios.delete(`http://localhost:8000/priorities/${id}`);
      fetch();
    } catch (e) {
      console.error(e);
      // Показать сообщение об ошибке
    }
  };

  useEffect(() => { fetch(); }, []);

  return (
    <div>
      <h2>Приоритетные документы</h2>
      <input placeholder="Ключевое слово" value={keyword} onChange={e => setKeyword(e.target.value)} />
      <input placeholder="Имя файла" value={docname} onChange={e => setDocname(e.target.value)} />
      <button onClick={add}>Добавить</button>

      <h3>Текущие приоритеты</h3>
      <ul>
        {priorities.map((p, i) => (
          <li key={i}>
            <strong>{p.keyword}</strong> → {p.document_name}
            <button onClick={() => remove(p.id)}>Удалить</button>
          </li>
        ))}
      </ul>
    </div>
  );
}