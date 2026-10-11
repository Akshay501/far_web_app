from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, data):
        if data:
            self.id = data['UserID']
            self.professor_key = data.get('ProfessorKey')
            self.role = data['Role']
            self.email = data['Email']
            # Clarkson NetID for CAS login; None until one is recorded.
            self.netid = data.get('NetID')