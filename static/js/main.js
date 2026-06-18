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

// Edit Record - supports all types (modal-based, legacy)
function editRecord(type, id) {
    let url = '';
    let modalTitle = 'Edit Record';

    switch(type) {
        case 'personal_award':  url = `/professor/awards/personal/edit/${id}`; modalTitle = 'Edit Personal Award'; break;
        case 'student_award':   url = `/professor/awards/student/edit/${id}`; modalTitle = 'Edit Student Award'; break;
        case 'current_student': url = `/professor/scholarship/edit/current_student/${id}`; modalTitle = 'Edit Current Student'; break;
        case 'thesis':          url = `/professor/scholarship/edit/thesis/${id}`; modalTitle = 'Edit Thesis'; break;
        case 'grant':           url = `/professor/grants/edit/${id}`; modalTitle = 'Edit Grant'; break;
        case 'proposal':        url = `/professor/proposals/edit/${id}`; modalTitle = 'Edit Proposal'; break;
        case 'service':         url = `/professor/service/edit/${id}`; modalTitle = 'Edit Service'; break;
        case 'review':          url = `/professor/reviews/edit/${id}`; modalTitle = 'Edit Review'; break;
        case 'advisee_count':   url = `/professor/advisee-count/edit/${id}`; modalTitle = 'Edit Advisee Count'; break;
        case 'prof_dev':        url = `/professor/professional-development/edit/${id}`; modalTitle = 'Edit Professional Development'; break;
        case 'prospective':     url = `/professor/prospective-visit/edit/${id}`; modalTitle = 'Edit Prospective Visit'; break;
        case 'undergrad':       url = `/professor/undergraduate-research/edit/${id}`; modalTitle = 'Edit Undergraduate Research'; break;
        default:
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

// Initialize DataTables — only on tables with .datatable class
// Skip any table that contains inline edit rows (d-none rows with colspan)
$(document).ready(function() {
    $('.datatable').each(function() {
        // Don't initialize if table has any edit rows (they break DataTables)
        if ($(this).find('tr[id*="-edit-"]').length === 0) {
            $(this).DataTable({
                pageLength: 10,
                ordering: true,
                searching: true
            });
        }
    });
});


// ====================== INLINE EDIT ======================

function inlineEdit(type, id) {
    document.getElementById(type + '-row-' + id).classList.add('d-none');
    document.getElementById(type + '-edit-' + id).classList.remove('d-none');
}

function cancelInlineEdit(type, id) {
    document.getElementById(type + '-edit-' + id).classList.add('d-none');
    document.getElementById(type + '-row-' + id).classList.remove('d-none');
}

function saveInlineEdit(type, id, fields) {
    const data = new FormData();
    data.append('inline_edit', '1');

    fields.forEach(field => {
        const el = document.getElementById(type + '-' + field + '-' + id);
        if (el) data.append(field, el.value);
    });

    const urlMap = {
        'service':         '/professor/service/edit/' + id,
        'review':          '/professor/reviews/edit/' + id,
        'prof_dev':        '/professor/professional-development/edit/' + id,
        'undergrad':       '/professor/undergraduate-research/edit/' + id,
        'grant':           '/professor/grants/edit/' + id,
        'proposal':        '/professor/proposals/edit/' + id,
        'personal_award':  '/professor/awards/personal/edit/' + id,
        'student_award':   '/professor/awards/student/edit/' + id,
        'current_student': '/professor/scholarship/edit/current_student/' + id,
        'thesis':          '/professor/scholarship/edit/thesis/' + id,
    };

    const url = urlMap[type];
    if (!url) { alert('Unknown type: ' + type); return; }

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    data.append('csrf_token', csrf);

    fetch(url, { method: 'POST', body: data, credentials: 'same-origin' })
        .then(response => {
            if (response.ok || response.redirected) {
                const finalUrl = response.url || window.location.href;
                const separator = finalUrl.includes('?') ? '&' : '?';
                const highlightUrl = finalUrl + separator + '_t=' + Date.now() + '&highlight=' + type + '-' + id;
                window.location.href = highlightUrl;
            } else {
                alert('Save failed. Please try again.');
            }
        })
        .catch(() => alert('Network error. Please try again.'));
}


// ====================== DUPLICATE ======================

function duplicateRecord(type, id) {
    const urlMap = {
        'service':         `/professor/service/duplicate/${id}`,
        'review':          `/professor/reviews/duplicate/${id}`,
        'prof_dev':        `/professor/professional-development/duplicate/${id}`,
        'undergrad':       `/professor/undergraduate-research/duplicate/${id}`,
        'grant':           `/professor/grants/duplicate/${id}`,
        'proposal':        `/professor/proposals/duplicate/${id}`,
        'personal_award':  `/professor/awards/personal/duplicate/${id}`,
        'student_award':   `/professor/awards/student/duplicate/${id}`,
        'current_student': `/professor/scholarship/duplicate/current_student/${id}`,
        'thesis':          `/professor/scholarship/duplicate/thesis/${id}`,
    };

    const url = urlMap[type];
    if (!url) { alert('Unknown type: ' + type); return; }

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const data = new FormData();
    data.append('csrf_token', csrf);

    fetch(url, { method: 'POST', body: data, credentials: 'same-origin' })
        .then(response => {
            if (response.ok || response.redirected) {
                const finalUrl = response.url || window.location.href;
                const separator = finalUrl.includes('?') ? '&' : '?';
                window.location.href = finalUrl + separator + '_t=' + Date.now();
            } else {
                alert('Duplicate failed. Please try again.');
            }
        })
        .catch(() => alert('Network error. Please try again.'));
}


// ====================== HIGHLIGHT SAVED ROW ======================
// After save, URL has ?highlight=type-id (e.g. personal_award-5)
// Row IDs in templates: type-row-id (e.g. personal_award-row-5)
// Works inside Bootstrap tab panes by activating the tab first.

document.addEventListener('DOMContentLoaded', function() {
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get('highlight');
    if (!highlight) return;

    const lastDash = highlight.lastIndexOf('-');
    const type = highlight.substring(0, lastDash);
    const id = highlight.substring(lastDash + 1);
    const rowId = type + '-row-' + id;

    // Clean the URL immediately
    const cleanUrl = window.location.href
        .replace(/[&?]highlight=[^&]*/g, '')
        .replace(/[&?]_t=[^&]*/g, '')
        .replace(/\?&/, '?').replace(/[?&]$/, '');
    window.history.replaceState({}, '', cleanUrl);

    function flashRow() {
        const row = document.getElementById(rowId);
        if (!row) return;
        if (row.classList.contains('d-none')) return;

        row.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Add highlight class (gold background with !important overrides Bootstrap)
        row.classList.add('row-highlight');

        // After 3 seconds, remove the class to trigger the CSS fade-out transition
        setTimeout(() => {
            row.classList.remove('row-highlight');
        }, 3000);
    }

    const row = document.getElementById(rowId);
    if (!row) return;

    const pane = row.closest('.tab-pane');
    if (pane && !pane.classList.contains('active')) {
        const paneId = pane.id;
        const tabBtn = document.querySelector(`[data-bs-target="#${paneId}"], [href="#${paneId}"]`);
        if (tabBtn) {
            tabBtn.click();
            setTimeout(flashRow, 400);
        } else {
            flashRow();
        }
    } else {
        flashRow();
    }
});
