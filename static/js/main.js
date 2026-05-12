// Main JavaScript for FAR application

// Show Add New modal
function showAddModal(type) {
    let url = '';
    if (type === 'current_student') {
        url = '/professor/scholarship/add/current_student';
    } else if (type === 'thesis') {
        url = '/professor/scholarship/add/thesis';
    } else {
        alert('Unknown record type');
        return;
    }

    fetch(url)
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalBody').innerHTML = html;
            document.getElementById('modalTitle').textContent = type === 'current_student' ? 'Add New Student' : 'Add New Thesis';
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        });
}

// Edit Record - supports all types
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
        case 'current_student':
            url = `/professor/scholarship/edit/current_student/${id}`;
            modalTitle = 'Edit Current Student';
            break;
        case 'thesis':
            url = `/professor/scholarship/edit/thesis/${id}`;
            modalTitle = 'Edit Thesis';
            break;
        case 'grant':
            url = `/professor/grants/edit/${id}`;
            modalTitle = 'Edit Grant';
            break;
        case 'proposal':
            url = `/professor/proposals/edit/${id}`;
            modalTitle = 'Edit Proposal';
            break;
        case 'service':
            url = `/professor/service/edit/${id}`;
            modalTitle = 'Edit Service';
            break;
        case 'review':
            url = `/professor/reviews/edit/${id}`;
            modalTitle = 'Edit Review';
            break;
        case 'advisee_count':
            url = `/professor/advisee-count/edit/${id}`;
            modalTitle = 'Edit Advisee Count';
            break;
        case 'prof_dev':
            url = `/professor/professional-development/edit/${id}`;
            modalTitle = 'Edit Professional Development';
            break;
        case 'prospective':
            url = `/professor/prospective-visit/edit/${id}`;
            modalTitle = 'Edit Prospective Visit';
            break;
        case 'undergrad':
            url = `/professor/undergraduate-research/edit/${id}`;
            modalTitle = 'Edit Undergraduate Research';
            break;
        default:
            console.error('Unknown record type:', type);
            alert('Unknown record type: ' + type);
            return;
    }

    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.text();
        })
        .then(html => {
            document.getElementById('modalTitle').textContent = modalTitle;
            document.getElementById('modalBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        })
        .catch(error => {
            console.error('Edit form failed:', error);
            alert('Failed to load the edit form. Please check console (F12).');
        });
}

// Delete Record - supports all types
function deleteRecord(type, id, label) {
    let name = label || type;
    if (!confirm(`Are you sure you want to delete "${name}"?`)) return;

    let url = '';
    switch(type) {
        case 'personal_award':  url = `/professor/awards/personal/delete/${id}`; break;
        case 'student_award':   url = `/professor/awards/student/delete/${id}`; break;
        case 'current_student': url = `/professor/scholarship/delete/current_student/${id}`; break;
        case 'thesis':          url = `/professor/scholarship/delete/thesis/${id}`; break;
        case 'grant':           url = `/professor/grants/delete/${id}`; break;
        case 'proposal':        url = `/professor/proposals/delete/${id}`; break;
        case 'service':         url = `/professor/service/delete/${id}`; break;
        case 'review':          url = `/professor/reviews/delete/${id}`; break;
        case 'advisee_count':   url = `/professor/advisee-count/delete/${id}`; break;
        case 'prof_dev':        url = `/professor/professional-development/delete/${id}`; break;
        case 'prospective':     url = `/professor/prospective-visit/delete/${id}`; break;
        case 'undergrad':       url = `/professor/undergraduate-research/delete/${id}`; break;
        default:
            alert('Unknown record type: ' + type);
            return;
    }

    fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
    }).then(() => location.reload());
}

// Initialize DataTables
$(document).ready(function() {
    $('.datatable').DataTable({
        pageLength: 10,
        ordering: true,
        searching: true
    });
});
