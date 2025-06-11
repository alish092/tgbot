import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SynonymManager from './SynonymManager';
import PriorityManager from './PriorityManager';
import UserManager from './UserManager';
import Pagination from './Pagination';
import StatsDashboard from './StatsDashboard';



function AdminPanel() {
  const [activeTab, setActiveTab] = useState('logs');
  const [logs, setLogs] = useState([]);
  const [totalLogs, setTotalLogs] = useState(0); // Общее количество логов для пагинации
  const [page, setPage] = useState(1);            // Страница
  const [limit, setLimit] = useState(20);         // Лимит на странице
  const [complaints, setComplaints] = useState([]);
  const [overrides, setOverrides] = useState([]);
  const [search, setSearch] = useState('');
  const [synonyms, setSynonyms] = useState([]);
  const [priorities, setPriorities] = useState([]);
  const [newOverrideQuestion, setNewOverrideQuestion] = useState('');
  const [newOverrideAnswer, setNewOverrideAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editingOverride, setEditingOverride] = useState(null);
  const [editQuestion, setEditQuestion] = useState('');
  const [editAnswer, setEditAnswer] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [manualResponse, setManualResponse] = useState('');
  const [processingComplaint, setProcessingComplaint] = useState(false)
  const [usernameFilter, setUsernameFilter] = useState('');
  const [questionFilter, setQuestionFilter] = useState('');
  const [answerFilter, setAnswerFilter] = useState('');
  const cancelManualResponse = () => {
  setSelectedComplaint(null);
  setManualResponse('');
};

  const fetchOverrides = async () => {
  console.log("📡 Получаем overrides...");
  const res = await axios.get('http://localhost:8000/overrides');
  console.log("📦 Получены overrides:", res.data);
  setOverrides(res.data);
};

  const handleComplaintResponse = (complaint) => {
  setSelectedComplaint(complaint);
  setManualResponse(complaint.answer || ''); // Предзаполняем текущим ответом
};

  const addOverride = async () => {
     console.log("🧪 Запуск addOverride...");

  setLoading(true);
  try {
    console.log("🔥 Пытаюсь отправить override...");
    console.log("📤 Отправка запроса с данными:", newOverrideQuestion, newOverrideAnswer);

    const response = await axios.post("http://localhost:8000/overrides", null, {
      params: {
        question: newOverrideQuestion,
        answer: newOverrideAnswer
      }
    });

    console.log("✅ Override добавлен:", response.data);
    setNewOverrideQuestion('');
    setNewOverrideAnswer('');
    await fetchOverrides();
    setActiveTab('overrides');

  } catch (error) {

    console.error("❌ Ошибка при добавлении override:", error.response?.data || error.message);
    setError("Не удалось добавить ручной ответ: " + (error.response?.data?.detail || error.message));
  } finally {
    setLoading(false);
  }
};

  // Функция для отправки ручного ответа на жалобу
  const sendManualResponse = async () => {
  if (!selectedComplaint || !manualResponse.trim()) return;

  setProcessingComplaint(true);
  setError(null);

  try {
    const complaintId = Number(selectedComplaint.id);
    if (!Number.isInteger(complaintId) || complaintId <= 0) {
      throw new Error('Некорректный ID жалобы');
    }

    const response = await axios.post(
      `http://localhost:8000/complaints/${complaintId}/override`,
      { manual_response: manualResponse }
    );

    if (response.data && response.data.success) {
      fetchComplaints();
      setSelectedComplaint(null);
      setManualResponse('');
      alert('Ручной ответ успешно отправлен пользователю');
    } else {
      setError('Не удалось отправить ручной ответ: ' + (response.data?.detail || 'Неизвестная ошибка'));
    }
  } catch (error) {
    console.error('Ошибка при отправке ручного ответа:', error);
    setError('Не удалось отправить ручной ответ: ' + (error.response?.data?.detail || error.message));
  } finally {
    setProcessingComplaint(false);
  }
};

  // Функция удаления override
  const deleteOverride = async (id) => {
    try {
      await axios.delete(`http://localhost:8000/overrides/${id}`);
      fetchOverrides();
    } catch (e) {
      console.error("Ошибка при удалении override:", e);
      setError("Не удалось удалить ручной ответ");
    }
  };
  const startEditOverride = (override) => {
    setEditingOverride(override);
    setEditQuestion(override.question);
    setEditAnswer(override.answer);
  };

  // Создание override из жалобы
  const createOverrideFromComplaint = (c) => {
  // префилл формы и сразу переключаем вкладку
  setNewOverrideQuestion(c.question);
  setNewOverrideAnswer(c.answer || "");
  setActiveTab("overrides");
};
  const saveEditedOverride = async () => {
  try {
    await axios.put(`http://localhost:8000/overrides/${editingOverride.id}`, null, {
      params: {
        question: editQuestion,
        answer: editAnswer,
      }
    });
    setEditingOverride(null);
    fetchOverrides();
  } catch (error) {
    console.error('Ошибка при сохранении изменений:', error);
    setError('Не удалось сохранить изменения');
    }
  };


const fetchLogs = async () => {
  try {
    setLoading(true);
    const res = await axios.get('http://localhost:8000/logs', {
      params: {
        page,
        limit,
        search,
        username: usernameFilter,
        question: questionFilter,
        answer: answerFilter
      }
    });
    setLogs(res.data.items);
    setTotalLogs(res.data.total);
  } catch (error) {
    console.error('Ошибка при загрузке логов:', error);
    setError('Ошибка при загрузке логов');
  } finally {
    setLoading(false);
  }
};


  const fetchComplaints = () =>
  axios.get('http://localhost:8000/complaints')
    .then(res => {
      console.log('Данные жалоб:', res.data); // для отладки
      // Проверяем, что полученные данные - это массив
      if (Array.isArray(res.data)) {
        // Проверяем корректность данных и добавляем значения по умолчанию
        const validComplaints = res.data.map(complaint => ({
          id: complaint.id || 0,
          username: complaint.username || 'Неизвестно',
          question: complaint.question || 'Нет вопроса',
          answer: complaint.answer || 'Нет ответа',
          status: complaint.status || 'PENDING',
          complaint: complaint.complaint || 'Нет текста жалобы'
        }));
        setComplaints(validComplaints);
      } else {
        console.error('Получены неверные данные:', res.data);
        setComplaints([]); // Устанавливаем пустой массив в случае ошибки
      }
    })
    .catch(error => {
      console.error('Ошибка при загрузке жалоб:', error);
      setComplaints([]); // Устанавливаем пустой массив в случае ошибки
    });



  const fetchSynonyms = () =>
    axios.get('http://localhost:8000/synonyms_from_db').then(res => setSynonyms(res.data));

  const fetchPriorities = () =>
    axios.get('http://localhost:8000/priorities').then(res => setPriorities(res.data));

  const handlePageChange = (page) => {
  setCurrentPage(page);
  fetchLogs(page, pageSize, filter);
};
  const exportData = (format) => {
  // Создаем ссылку на API для экспорта
  const exportUrl = `http://localhost:8000/logs/export?format=${format}&search=${search}`;

  // Создаем временную ссылку и эмулируем клик для скачивания
  const link = document.createElement('a');
  link.href = exportUrl;
  link.target = '_blank';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
  useEffect(() => {
  const fetchAllData = async () => {
    try {
      setLoading(true);
      await fetchLogs();
      await fetchComplaints();
      await fetchOverrides();
      await fetchSynonyms();
      await fetchPriorities();
    } catch (error) {
      console.error("Ошибка при получении данных:", error);
      setError("Не удалось загрузить данные");
    } finally {
      setLoading(false);
    }
  };

  fetchAllData();
}, [activeTab, page, limit, search, usernameFilter, questionFilter, answerFilter]); // Добавляем новые зависимости

  useEffect(() => {
  if (activeTab === 'complaints') {
    console.log('Загрузка жалоб из-за изменения вкладки');
    fetchComplaints();
  }
}, [activeTab]);

  const renderLogs = () => {
    if (!logs || !Array.isArray(logs)) {
            console.log("🟢 ЭТО ИМЕННО МОЙ КОД");
      return <p>Нет данных для отображения</p>;
    }

    return (
        <div>
          <h2>📄 Логи</h2>

          {/* Форма фильтрации */}
          <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f9f9f9', borderRadius: '5px' }}>
            <h3>Фильтрация логов</h3>
            <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
              <input
                type="text"
                placeholder="Фильтр по пользователю"
                value={usernameFilter}
                onChange={(e) => setUsernameFilter(e.target.value)}
                style={{ padding: '8px', width: '33%' }}
              />
              <input
                type="text"
                placeholder="Фильтр по вопросу"
                value={questionFilter}
                onChange={(e) => setQuestionFilter(e.target.value)}
                style={{ padding: '8px', width: '33%' }}
              />
              <input
                type="text"
                placeholder="Фильтр по ответу"
                value={answerFilter}
                onChange={(e) => setAnswerFilter(e.target.value)}
                style={{ padding: '8px', width: '33%' }}
              />
            </div>
            <button
              onClick={fetchLogs}
              style={{ padding: '8px 15px', backgroundColor: '#4CAF50', color: 'white', border: 'none', cursor: 'pointer', marginRight: '10px' }}
            >
              Применить фильтры
            </button>
            <button
              onClick={() => {
                setUsernameFilter('');
                setQuestionFilter('');
                setAnswerFilter('');
                // Сбросим поисковый запрос тоже
                setSearch('');
                fetchLogs();
              }}
              style={{ padding: '8px 15px', backgroundColor: '#f44336', color: 'white', border: 'none', cursor: 'pointer' }}
            >
              Сбросить фильтры
            </button>
          </div>

          {loading ? (
              <p>Идёт загрузка...</p>
          ) : (
              <table style={{width: '100%', borderCollapse: 'collapse', marginTop: '10px'}}>
                <thead>
                <tr style={{backgroundColor: '#f2f2f2'}}>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Question</th>
                  <th>Answer</th>
                </tr>
                </thead>
                <tbody>
                {logs.length > 0 ? (
                    logs.map((log) => (
                        <tr key={log.id}>
                          <td>{log.id}</td>
                          <td>{log.username}</td>
                          <td>{log.question}</td>
                          <td>{log.answer}</td>
                        </tr>
                    ))
                ) : (
                    <tr>
                      <td colSpan="4" style={{textAlign: 'center'}}>
                        Нет доступных данных
                      </td>
                    </tr>
                )}
                </tbody>
              </table>
          )}
        </div>
    );
  };


  const renderComplaints = () => {
  // Проверяем, что complaints существует и является массивом
  const complaintsArray = Array.isArray(complaints) ? complaints : [];

  return (
    <div>
      <h2>🚫 Жалобы</h2>

      {/* Форма для ручного ответа на жалобу */}
      {selectedComplaint && (
        <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f0f8ff', borderRadius: '5px', border: '1px solid #c0d6e4' }}>
          <h3>Ручной ответ на жалобу</h3>

          <div style={{ marginBottom: '15px' }}>
            <p><strong>Пользователь:</strong> {selectedComplaint.username}</p>
            <p><strong>Вопрос:</strong> {selectedComplaint.question}</p>
            <p><strong>Текущий ответ:</strong> {selectedComplaint.answer}</p>
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label htmlFor="manualResponse" style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Ваш ответ:</label>
            <textarea
              id="manualResponse"
              value={manualResponse}
              onChange={(e) => setManualResponse(e.target.value)}
              style={{ width: '100%', padding: '8px', minHeight: '120px', borderRadius: '4px', border: '1px solid #ccc' }}
              placeholder="Введите ваш ответ пользователю..."
            />
          </div>

          {error && <div style={{ color: 'red', marginBottom: '10px' }}>{error}</div>}

          <div>
            <button
              onClick={sendManualResponse}
              disabled={processingComplaint || !manualResponse.trim()}
              style={{
                padding: '8px 15px',
                backgroundColor: '#4CAF50',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: processingComplaint || !manualResponse.trim() ? 'not-allowed' : 'pointer',
                marginRight: '10px',
                opacity: processingComplaint || !manualResponse.trim() ? 0.7 : 1
              }}
            >
              {processingComplaint ? 'Отправка...' : 'Отправить ответ'}
            </button>

            <button
              onClick={cancelManualResponse}
              style={{
                padding: '8px 15px',
                backgroundColor: '#f44336',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {complaintsArray.length === 0 ? (
        <p>Нет доступных жалоб</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '10px' }}>
          <thead>
            <tr style={{ backgroundColor: '#f2f2f2' }}>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>ID</th>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Пользователь</th>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Вопрос</th>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Ответ</th>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Статус</th>
              <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Действия</th>
            </tr>
          </thead>
          <tbody>
            {complaintsArray.map((c) => (
              <tr key={c.id} style={{ borderBottom: '1px solid #ddd' }}>
                <td style={{ padding: '8px' }}>{c.id}</td>
                <td style={{ padding: '8px' }}>{c.username}</td>
                <td style={{ padding: '8px' }}>{c.question}</td>
                <td style={{ padding: '8px' }}>{c.answer}</td>
                <td style={{ padding: '8px' }}>
  <span style={{
    display: 'inline-block',
    padding: '4px 8px',
    borderRadius: '4px',
    backgroundColor:
      c.status === 'RESOLVED' ? '#8bc34a' :
      c.status === 'REJECTED' ? '#ff9800' :
      '#f44336',
    color: 'white',
    fontSize: '12px',
    fontWeight: 'bold'
  }}>
    {c.status === 'RESOLVED' ? 'Решено' :
     c.status === 'REJECTED' ? 'Отклонено' :
     'Ожидает'}
  </span>
</td>
                <td style={{ padding: '8px' }}>
                  {c.status === 'PENDING' && (
                    <button
                      onClick={() => handleComplaintResponse(c)}
                      style={{
                        padding: '5px 10px',
                        backgroundColor: '#2196F3',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        marginRight: '5px'
                      }}
                    >
                      Ответить
                    </button>
                  )}
                  <button
                    onClick={() => createOverrideFromComplaint(c)}
                    style={{
                      padding: '5px 10px',
                      backgroundColor: '#4CAF50',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    В ручные ответы
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};



  const renderOverrides = () => (
  <div>
    <h2>✍️ Ручные ответы</h2>

    {error && <div style={{ color: 'red', marginBottom: '10px' }}>{error}</div>}

    {/* Блок добавления нового ответа */}
    <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f9f9f9', borderRadius: '5px' }}>
      <h3>Добавить новый ручной ответ</h3>
      <div style={{ marginBottom: '10px' }}>
        <input
          type="text"
          placeholder="Вопрос"
          value={newOverrideQuestion}
          onChange={(e) => setNewOverrideQuestion(e.target.value)}
          style={{ width: '100%', padding: '8px', marginBottom: '5px' }}
        />
      </div>
      <div style={{ marginBottom: '10px' }}>
        <textarea
          placeholder="Ответ"
          value={newOverrideAnswer}
          onChange={(e) => setNewOverrideAnswer(e.target.value)}
          style={{ width: '100%', padding: '8px', height: '100px' }}
        />
      </div>
      <button
        onClick={addOverride}
        disabled={loading || !newOverrideQuestion.trim() || !newOverrideAnswer.trim()}
        style={{ padding: '8px 15px', backgroundColor: '#4CAF50', color: 'white', border: 'none', cursor: 'pointer' }}
      >
        {loading ? 'Добавление...' : 'Добавить ручной ответ'}
      </button>
    </div>

    {/* Блок редактирования ответа */}
    {editingOverride && (
      <div style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#e8f0fe', borderRadius: '5px' }}>
        <h3>Редактировать ручной ответ</h3>
        <div style={{ marginBottom: '10px' }}>
          <input
            type="text"
            placeholder="Вопрос"
            value={editQuestion}
            onChange={(e) => setEditQuestion(e.target.value)}
            style={{ width: '100%', padding: '8px', marginBottom: '5px' }}
          />
        </div>
        <div style={{ marginBottom: '10px' }}>
          <textarea
            placeholder="Ответ"
            value={editAnswer}
            onChange={(e) => setEditAnswer(e.target.value)}
            style={{ width: '100%', padding: '8px', height: '100px' }}
          />
        </div>
        <button
          onClick={saveEditedOverride}
          style={{ padding: '8px 15px', backgroundColor: '#4CAF50', color: 'white', border: 'none', cursor: 'pointer', marginRight: '10px' }}
        >
          Сохранить
        </button>
        <button
          onClick={() => setEditingOverride(null)}
          style={{ padding: '8px 15px', backgroundColor: '#f44336', color: 'white', border: 'none', cursor: 'pointer' }}
        >
          Отмена
        </button>
      </div>
    )}

    {/* Таблица ручных ответов */}
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr style={{ backgroundColor: '#f2f2f2' }}>
          <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>ID</th>
          <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Вопрос</th>
          <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Ответ</th>
          <th style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #ddd' }}>Действия</th>
        </tr>
      </thead>
      <tbody>
        {overrides.map((o) => (
          <tr key={o.id} style={{ borderBottom: '1px solid #ddd' }}>
            <td style={{ padding: '8px' }}>{o.id}</td>
            <td style={{ padding: '8px' }}>{o.question}</td>
            <td style={{ padding: '8px' }}>{o.answer}</td>
            <td style={{ padding: '8px' }}>
              <button
                onClick={() => startEditOverride(o)}
                style={{ marginRight: '10px', padding: '5px 10px', backgroundColor: '#2196F3', color: 'white', border: 'none', cursor: 'pointer' }}
              >
                Редактировать
              </button>
              <button
                onClick={() => deleteOverride(o.id)}
                style={{ padding: '5px 10px', backgroundColor: '#f44336', color: 'white', border: 'none', cursor: 'pointer' }}
              >
                Удалить
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);


;
  return (
    <div style={{ paddingTop: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>⚙️ Админ-панель</h1>
      <div style={{ marginBottom: '20px' }}>
        <button
          onClick={() => setActiveTab('logs')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'logs' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'logs' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          📄 Логи
        </button>
        <button
          onClick={() => setActiveTab('complaints')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'complaints' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'complaints' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          🚫 Жалобы
        </button>
        <button
          onClick={() => setActiveTab('overrides')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'overrides' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'overrides' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          ✍️ Ручные ответы
        </button>
        <button
          onClick={() => setActiveTab('synonyms')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'synonyms' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'synonyms' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          Синонимы
        </button>
        <button
          onClick={() => setActiveTab('priorities')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'priorities' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'priorities' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          Приоритеты
        </button>
        <button
          onClick={() => setActiveTab('training')}
          style={{
            padding: '8px 15px',
            backgroundColor: activeTab === 'training' ? '#2196F3' : '#e0e0e0',
            color: activeTab === 'training' ? 'white' : 'black',
            border: 'none',
            margin: '0 5px 5px 0',
            cursor: 'pointer'
          }}
        >
          📚 Обучение
        </button>
        <button
            onClick={() => setActiveTab('users')}
            style={{
                padding: '8px 15px',
                backgroundColor: activeTab === 'users' ? '#2196F3' : '#e0e0e0',
                color: activeTab === 'users' ? 'white' : 'black',
                border: 'none',
                margin: '0 5px 5px 0',
                cursor: 'pointer'
         }}
>
  👤 Пользователи
</button>
<button
  onClick={() => setActiveTab('stats')}
  style={{
    padding: '8px 15px',
    backgroundColor: activeTab === 'stats' ? '#2196F3' : '#e0e0e0',
    color: activeTab === 'stats' ? 'white' : 'black',
    border: 'none',
    margin: '0 5px 5px 0',
    cursor: 'pointer'
  }}
>
  📊 Статистика
</button>
      </div>

      {activeTab === 'logs' && renderLogs()}
      {activeTab === 'complaints' && renderComplaints()}
      {activeTab === 'overrides' && renderOverrides()}
      {activeTab === 'synonyms' && <SynonymManager />}
      {activeTab === 'stats' && <StatsDashboard />}
      {activeTab === 'priorities' && <PriorityManager />}
      {activeTab === 'training' && (
        <div>
          <h2>🔁 Синонимы</h2>
          <ul>
            {Object.entries(
              synonyms.reduce((acc, { keyword, synonym }) => {
                acc[keyword] = [...(acc[keyword] || []), synonym];
                return acc;
              }, {})
            ).map(([keyword, syns]) => (
              <li key={keyword}>
                <b>{keyword}</b>: {syns.join(', ')}
              </li>
            ))}
          </ul>

          <h2>📌 Приоритетные документы</h2>
          <ul>
            {priorities.map((p, i) => (
              <li key={i}>
                <b>{p.keyword}</b>: {p.document_name}
              </li>
            ))}
          </ul>
        </div>

      )}
      {activeTab === 'users' && <UserManager />}


    </div>
  );
}

export default AdminPanel;