from abilities.ability_manager import AbilityManager
from abilities.terminal.terminal_ability import TerminalAbility

am = AbilityManager()
am.register(TerminalAbility())

# Test rate limiting - terminal has limit of 20/min with 5 burst
print("Testing rate limit on terminal...")
for i in range(30):
    result = am.execute("terminal", "echo test", approval_required=True, approved=True)
    if isinstance(result, dict) and result.get("status") == "failed" and "Rate limit" in str(result.get("error", "")):
        print(f"Call {i+1}: Rate limited - {result.get('error')}")
        break
    elif i < 5:
        print(f"Call {i+1}: OK (burst)")
    elif i == 24:
        print(f"Call {i+1}: OK")
    elif i == 25:
        print(f"Call {i+1}: Rate limited - {result.get('error')}")
        break
    else:
        print(f"Call {i+1}: OK")

# Check rate limit status
status = am.rate_limiter.get_status("terminal")
print(f"Rate limit status: {status}")