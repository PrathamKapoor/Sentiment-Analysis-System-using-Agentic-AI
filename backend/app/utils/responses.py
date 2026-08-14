from flask import jsonify


def success_response(data=None, message="Operation completed successfully", status_code=200):
    return jsonify({
        "success": True,
        "message": message,
        "data": data if data is not None else {},
    }), status_code


def error_response(code, message, status_code=400, details=None):
    return jsonify({
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        },
    }), status_code
