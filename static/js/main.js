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
        default:
            console.error('Unknown record type:', type);
            alert('Unknown record type');
            return;
    }

    console.log('🔍 Attempting to load edit form from:', url);

    fetch(url)
        .then(response => {
            console.log('📡 Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status} - ${response.statusText}`);
            }
            return response.text();
        })
        .then(html => {
            console.log('✅ Form loaded successfully');
            document.getElementById('modalTitle').textContent = modalTitle;
            document.getElementById('modalBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('actionModal')).show();
        })
        .catch(error => {
            console.error('❌ Edit form failed:', error);
            alert('Failed to load the edit form.\n\nCheck the browser console (F12) for details.');
        });
}