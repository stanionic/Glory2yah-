// Real-time updates using AJAX
function updateGrades(courseId) {
    fetch(`/api/grades/${courseId}`)
        .then(response => response.json())
        .then(data => {
            const tbody = document.querySelector('#grades-table tbody');
            tbody.innerHTML = '';
            data.forEach(grade => {
                const row = `<tr>
                    <td>${grade.student}</td>
                    <td>${grade.assignments || 'N/A'}</td>
                    <td>${grade.exam || 'N/A'}</td>
                    <td>${grade.average || 'N/A'}</td>
                </tr>`;
                tbody.innerHTML += row;
            });
        });
}

// Example: Update every 5 seconds for course ID 1
setInterval(() => updateGrades(1), 5000);
