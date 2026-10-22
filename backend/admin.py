import sys
from app import create_app
from models import db, User

app = create_app()


def cmd_list():
    for u in User.query.order_by(User.id).all():
        status = "已放行" if u.is_active else "待放行"
        print(f"{u.id}  {u.username}  {status}")


def find_user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        print(f"没有这个用户：{username}")
    return user


def cmd_approve(username):
    user = find_user(username)
    if user is None:
        return
    user.is_active = True
    db.session.commit()
    print(f"已放行：{username}")


def cmd_reject(username):
    user = find_user(username)
    if user is None:
        return
    db.session.delete(user)
    db.session.commit()
    print(f"已删除：{username}")


if __name__ == "__main__":
    USAGE = "用法: python admin.py list | approve <用户名> | reject <用户名>"

    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    command = sys.argv[1]

    with app.app_context():
        if command == "list":
            cmd_list()
        elif command in ("approve", "reject"):
            if len(sys.argv) < 3:
                print(USAGE)
                sys.exit(1)
            if command == "approve":
                cmd_approve(sys.argv[2])
            else:
                cmd_reject(sys.argv[2])
        else:
            print(USAGE)
            sys.exit(1)
