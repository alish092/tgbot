// UserManager.jsx
import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function UserManager() {
  const [users, setUsers] = useState([]);
  const [userId, setUserId] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('');

  const fetchUsers = async () => {
    try {
      const res = await axios.get('http://localhost:8000/roles');
      setUsers(res.data);
    } catch (error) {
      console.error('Ошибка при загрузке пользователей:', error);
    }
  };

  const addUser = async () => {
    if (!userId || !username || !role) {
      alert('Заполните все поля');
      return;
    }
    try {
      await axios.post("http://localhost:8000/roles", {
  user_id: Number(userId),
  username,
  role
});
      setUserId('');
      setUsername('');
      setRole('');
      fetchUsers();
    } catch (error) {
      console.error('Ошибка при добавлении пользователя:', error);
    }
  };

  const deleteUser = async (id) => {
    if (!window.confirm('Точно удалить пользователя?')) return;
    try {
      await axios.delete(`http://localhost:8000/roles/${id}`);
      fetchUsers();
    } catch (error) {
      console.error('Ошибка при удалении пользователя:', error);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return (
    <div>
      <h2>Пользователи</h2>
      <div style={{ marginBottom: '20px' }}>
        <input
          placeholder="User ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          style={{ marginRight: '10px' }}
        />
        <input
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ marginRight: '10px' }}
        />
        <input
          placeholder="Role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          style={{ marginRight: '10px' }}
        />
        <button onClick={addUser}>Добавить</button>
      </div>

      <table border="1" cellPadding="8">
        <thead>
          <tr>
            <th>ID</th>
            <th>Username</th>
            <th>Role</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.user_id}</td>
              <td>{user.username}</td>
              <td>{user.role}</td>
              <td>
                <button onClick={() => deleteUser(user.user_id)}>Удалить</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}