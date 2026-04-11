// static/js/main.js - Clean version for FAR app

function editRecord(type, id) {
    let url = '';
    let modalTitle = 'Edit Record';

    switch(type) {
        case 'personal_award':
            url = `/professor/awards/personal/edit/${id}`;
            modalTitle = 'Edit Personal Award';
            break;
        case 'student_award':
            url = `/professor/awards/student/edit/${id}`;
            modalTitle = 'Edit Student Award';
            break;
        case 'grant':
            url = `/professor/grants/edit/${id}`;
            modalTitle = 'Edit Grant';
            break;
        case 'teaching':
            url = `/professor/teaching/edit/${id}`;
            modalTitle = 'Edit Teaching Evaluation';
            break;
        default:
            alert('Unknown record type');
            return;
    }

    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error('Failed to load form');
            return response.text();
        })
        .then(html => {
            document.getElementById('modalTitle').textContent = modalTitle;
            document.getElementById('modalBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        })
        .catch(error => {
            console.error(error);
            alert('Failed to load the edit form. Please try again.');
        });
}

function deleteRecord(type, id, name = '') {
    const message = name 
        ? `Are you sure you want to delete "${name}"?` 
        : `Are you sure you want to delete this ${type}?`;

    if (!confirm(message)) return;

    let url = '';
    switch(type) {
        case 'personal_award':
            url = `/professor/awards/personal/delete/${id}`;
            break;
        case 'student_award':
            url = `/professor/awards/student/delete/${id}`;
            break;
        case 'grant':
            url = `/professor/grants/delete/${id}`;
            break;
        case 'teaching':
            url = `/professor/teaching/delete/${id}`;
            break;
        default:
            alert('Unknown record type for delete');
            return;
    }

    fetch(url, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    .then(response => {
        if (response.ok) {
            location.reload();   // Refresh to show updated list
        } else {
            alert('Failed to delete the record.');
        }
    })
    .catch(error => {
        console.error(error);
        alert('An error occurred while deleting.');
    });
}

// Initialize DataTables
document.addEventListener('DOMContentLoaded', function() {
    if (typeof $.fn !== 'undefined' && $.fn.DataTable) {
        $('.datatable').DataTable({
            pageLength: 10,
            responsive: true,
            ordering: true
        });
    }
});