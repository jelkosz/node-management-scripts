from werkzeug.security import generate_password_hash
import sys

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Exactly 2 arguments are expected: generate_user_pass.py <username> <password>\n")
        print("Example: python3 generate_user_pass.py someuser somepassword >> users")
    else:
        print(f'{sys.argv[1]}={generate_password_hash(sys.argv[2])}')
