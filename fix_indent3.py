with open('C:/Users/hp/HERCULE/change_proposal_manager.py', 'r') as f:
    content = f.read()

# Fix the _build_create_proposal method signature
old = '''    def _build_create_proposal(
        self,
        proposal: "ChangeProposal",
        destination_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":
        """Build CREATE_TEXT_FILE proposal with preview."""
        from change_proposals import ChangePreview, ChangeOperation, ProposalSta'''

new = '''    def _build_create_proposal(
        self,
        proposal: "ChangeProposal",
        destination_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":
        """Build CREATE_TEXT_FILE proposal with preview."""
        from change_proposals import ChangePreview, ChangeOperation, ProposalSta'''

content = content.replace(old, new)

with open('C:/Users/hp/HERCULE/change_proposal_manager.py', 'w') as f:
    f.write(content)
print('Fixed')