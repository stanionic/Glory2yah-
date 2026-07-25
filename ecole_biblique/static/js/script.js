// Real-time updates using AJAX - Ecole Biblique
function updateGrades(courseId) {
    fetch(`/ecole_biblique/api/grades/${courseId}`)
        .then(response => response.json())
        .then(data => {
            const tbody = document.querySelector('#grades-table tbody');
            if (!tbody) return;
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
        })
        .catch(err => console.error('Error fetching grades:', err));
}

// Only start auto-refresh if the grades table exists on the page
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('#grades-table')) {
        setInterval(() => updateGrades(1), 5000);
    }
});
