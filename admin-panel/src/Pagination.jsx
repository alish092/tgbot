import React from 'react';

const Pagination = ({ currentPage, totalPages, onPageChange }) => {
  // Определяем диапазон страниц для отображения
  const pageRange = 5; // Количество страниц, отображаемых слева и справа от текущей

  const getPageNumbers = () => {
    const pages = [];

    // Всегда показываем первую страницу
    pages.push(1);

    let startPage = Math.max(2, currentPage - pageRange);
    let endPage = Math.min(totalPages - 1, currentPage + pageRange);

    // Если мы близко к началу, показываем больше страниц в конце
    if (currentPage - pageRange < 2) {
      endPage = Math.min(totalPages - 1, 2 * pageRange + 1);
    }

    // Если мы близко к концу, показываем больше страниц в начале
    if (currentPage + pageRange >= totalPages - 1) {
      startPage = Math.max(2, totalPages - 2 * pageRange);
    }

    // Добавляем многоточие после первой страницы, если нужно
    if (startPage > 2) {
      pages.push('...');
    }

    // Добавляем промежуточные страницы
    for (let i = startPage; i <= endPage; i++) {
      pages.push(i);
    }

    // Добавляем многоточие перед последней страницей, если нужно
    if (endPage < totalPages - 1) {
      pages.push('...');
    }

    // Всегда показываем последнюю страницу
    if (totalPages > 1) {
      pages.push(totalPages);
    }

    return pages;
  };

  const handlePageClick = (page) => {
    if (page !== '...' && page !== currentPage) {
      onPageChange(page);
    }
  };

  // Если страница всего одна, не показываем пагинацию
  if (totalPages <= 1) {
    return null;
  }

  const pageNumbers = getPageNumbers();

  return (
    <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center' }}>
      {/* Кнопка "Назад" */}
      <button
        onClick={() => handlePageClick(currentPage - 1)}
        disabled={currentPage === 1}
        style={{
          padding: '5px 10px',
          margin: '0 5px',
          border: '1px solid #ccc',
          borderRadius: '3px',
          backgroundColor: currentPage === 1 ? '#f0f0f0' : 'white',
          cursor: currentPage === 1 ? 'default' : 'pointer',
          color: currentPage === 1 ? '#aaa' : '#333'
        }}
      >
        &laquo; Назад
      </button>

      {/* Номера страниц */}
      {pageNumbers.map((page, index) => (
        <button
          key={index}
          onClick={() => handlePageClick(page)}
          disabled={page === '...'}
          style={{
            padding: '5px 10px',
            margin: '0 2px',
            border: '1px solid #ccc',
            borderRadius: '3px',
            backgroundColor: page === currentPage ? '#2196F3' : 'white',
            cursor: page === '...' || page === currentPage ? 'default' : 'pointer',
            color: page === currentPage ? 'white' : '#333'
          }}
        >
          {page}
        </button>
      ))}

      {/* Кнопка "Вперед" */}
      <button
        onClick={() => handlePageClick(currentPage + 1)}
        disabled={currentPage === totalPages}
        style={{
          padding: '5px 10px',
          margin: '0 5px',
          border: '1px solid #ccc',
          borderRadius: '3px',
          backgroundColor: currentPage === totalPages ? '#f0f0f0' : 'white',
          cursor: currentPage === totalPages ? 'default' : 'pointer',
          color: currentPage === totalPages ? '#aaa' : '#333'
        }}
      >
        Вперед &raquo;
      </button>
    </div>
  );
};

export default Pagination;