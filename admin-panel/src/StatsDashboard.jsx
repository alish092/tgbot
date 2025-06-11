import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';

const StatsDashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const response = await axios.get('http://localhost:8000/stats');
        setStats(response.data);
        setError(null);
      } catch (err) {
        console.error('Ошибка при загрузке статистики:', err);
        setError('Не удалось загрузить статистику');
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);

  if (loading) return <div>Загрузка статистики...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!stats) return <div>Нет данных для отображения</div>;

  const usageData = [
    { name: 'Сегодня', запросы: stats.stats_today || 0 },
    { name: 'За неделю', запросы: stats.stats_week || 0 },
    { name: 'За месяц', запросы: stats.stats_month || 0 },
  ];

  const topQuestionsData = Array.isArray(stats.top_questions)
    ? stats.top_questions.map(q => ({
        name: q.name || q.question || 'Без названия',
        запросы: q.запросы || q.count || 0
      }))
    : [];

  const pieData = [
    { name: 'С жалобами', value: stats.total_complaints || 0 },
    { name: 'Без жалоб', value: (stats.total_logs || 0) - (stats.total_complaints || 0) }
  ];

  return (
    <div style={{ padding: '20px' }}>
      <h2>📊 Статистика использования бота</h2>

      <div style={{ marginBottom: '20px' }}>
        <h3>Общая информация</h3>
        <div style={{ display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap' }}>
          <div style={{ padding: '20px', backgroundColor: '#f0f8ff', borderRadius: '5px', margin: '10px', minWidth: '200px' }}>
            <h4>Всего запросов</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.total_logs}</div>
          </div>
          <div style={{ padding: '20px', backgroundColor: '#f0fff0', borderRadius: '5px', margin: '10px', minWidth: '200px' }}>
            <h4>Жалоб</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
              {stats.total_complaints} ({stats.complaints_ratio}%)
            </div>
          </div>
          <div style={{ padding: '20px', backgroundColor: '#fff0f0', borderRadius: '5px', margin: '10px', minWidth: '200px' }}>
            <h4>Ручных ответов</h4>
            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.total_overrides}</div>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>Динамика использования</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={usageData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="запросы" fill="#8884d8" barSize={40} radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ marginBottom: '30px' }}>
        <h3>Популярные запросы</h3>
        {topQuestionsData.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart
              data={topQuestionsData}
              layout="vertical"
              margin={{ top: 20, right: 40, left: 180, bottom: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis
                dataKey="name"
                type="category"
                width={380}
                tick={{ fontSize: 13 }}
                interval={0}
              />
              <Tooltip
                formatter={(value, name) => [value, 'Количество запросов']}
                labelFormatter={(label) => label || 'Без названия'}
              />
              <Legend />
              <Bar
                dataKey="запросы"
                fill="#82ca9d"
                barSize={20}
                radius={[10, 10, 0, 0]}
                label={{ position: 'right', fill: '#333', fontSize: 12 }}
              />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p style={{ color: 'gray' }}>Нет популярных запросов для отображения</p>
        )}
      </div>

      <div>
        <h3>Доля жалоб</h3>
        {stats.total_logs > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value, name) => [value, name]} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <p>Недостаточно данных для отображения диаграммы жалоб.</p>
        )}
      </div>
    </div>
  );
};

export default StatsDashboard;
