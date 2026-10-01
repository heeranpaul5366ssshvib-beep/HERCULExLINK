import re

with open('C:/Users/hp/HERCULE/change_proposal_manager.py', 'r') as f:
    content = f.read()

# Fix the _build_create_proposal method signature
old = '''    def _build_create_proposal(
        self,
        proposal: "ChangeProposal",
        destination_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":'''

new = '''    def _build_create_proposal(
        self,
        proposal: "ChangeProposal",
        destination_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":'''

content = content.replace(old, new)

with open('C:/Users/hp/HERCULE/change_proposal_manager.py', 'w') as f:
    f.write(content)
print('Fixed')