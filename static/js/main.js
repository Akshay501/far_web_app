
function editRecord(type, id) {
    let url = '';
    if (type === 'award') url = `/professor/awards/edit/${id}`;
    else if (type === 'grant') url = `/professor/grants/edit/${id}`;
    else if (type === 'service') url = `/professor/service/edit/${id}`;

    fetch(url)
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalBody').innerHTML = html;
            document.getElementById('modalTitle').textContent = 'Edit Record';
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        });
}

function deleteRecord(type, id, name) {
    if (!confirm(`Are you sure you want to delete this ${type}? (${name})`)) return;

    fetch(`/professor/${type}s/delete/${id}`, { method: 'POST' })
        .then(response => {
            if (response.ok) {
                location.reload();
            } else {
                alert('Failed to delete record');
            }
        });
}

function editRecord(type, id) {
    fetch(`/professor/${type}s/edit/${id}`)
        .then(r => r.text())
        .then(html => {
            document.getElementById('modalBody').innerHTML = html;
            document.getElementById('modalTitle').textContent = `Edit ${type.charAt(0).toUpperCase() + type.slice(1)}`;
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        });
}

function deleteRecord(type, id, name = '') {
    if (confirm(`Delete this ${type}? ${name ? '(' + name + ')' : ''}`)) {
        fetch(`/professor/${type}s/delete/${id}`, { method: 'POST' })
            .then(() => location.reload());
    }
}