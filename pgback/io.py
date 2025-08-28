import sys
def confirm(jdbc_url: str, action: str, target: str) -> None:
    print(f"You are about to {action} the database defined by JDBC URL:")
    print(f"  {jdbc_url}")
    print(f"Using backup file: {target}")
    ans = input("Proceed? Type 'yes' to continue: ").strip().lower()
    if ans != "yes":
        print("Operation cancelled.")
        sys.exit(1)
