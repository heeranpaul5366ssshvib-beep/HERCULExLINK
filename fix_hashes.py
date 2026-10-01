with open('change_proposals.py', 'r') as f:
    content = f.read()

old = '''if isinstance(self.operation, str):
            self.operation = ChangeOperation(self.operation)
        if isinstance(self.state, str):
            self.state = ProposalState(self.state)
        if self.error_code and isinstance(self.error_code, str):
            self.error_code = ChangeErrorCode(self.error_code)
        if not self.proposal_hash:
            self.proposal_hash = self._compute_hash()
     
    def _compute_hash(self) -> str:
        """Compute deterministic hash of proposal content for integrity verification."""
        data = {
            "operation": self.operation.value,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "content_hash": self.content_hash,
            "source_hash": self.source_hash,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]'''

new = '''if isinstance(self.operation, str):
            self.operation = ChangeOperation(self.operation)
        if isinstance(self.state, str):
            self.state = ProposalState(self.state)
        if self.error_code and isinstance(self.error_code, str):
            self.error_code = ChangeErrorCode(self.error_code)
        if not self.proposal_hash:
            self.proposal_hash = self._compute_hash()
     
    def _compute_hash(self) -> str:
        """Compute deterministic hash of proposal content for integrity verification."""
        # Use content directly for hash computation to detect tampering
        content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16] if self.content else None
        data = {
            "operation": self.operation.value,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "content_hash": content_hash,
            "source_hash": self.source_hash,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]'''

content = content.replace(old, new)

with open('change_proposals.py', 'w') as f:
    f.write(content)
print('Replaced all occurrences')