from flask import Flask, request

app = Flask(__name__)


def get_request_ip():
    proxy_request_ip = request.environ.get("HTTP_X_FORWARDED_FOR")
    request_ip = request.environ.get("REMOTE_ADDR")
    return request.environ.get(proxy_request_ip, request_ip)


@app.route("/")
def hello():
    return (
            "<html><body><p>Web Tier is OK<br> "
            + "<div>Requester IP:"
            + get_request_ip()
            + "</div>"
            + "<div>Server IP:"
            + request.host
            + "</div>"
            + "</p></body></html>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True, use_debugger=False, use_reloader=True)
