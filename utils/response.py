class Response:
    HTTP_OK = 200
    HTTP_CREATED = 201
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_FORBIDDEN = 403
    HTTP_NOT_FOUND = 404
    HTTP_VALIDATION_ERROR = 422
    HTTP_SERVER_ERROR = 500    
    
    @staticmethod
    def Ok(data=None):
        return{
            "status" : Response.HTTP_OK,
            "success" : True,
            "data" : data
        }
        
    @staticmethod
    def Error(message=None, code=None):
        if code is None:
            code = Response.HTTP_BAD_REQUEST
        return{
            "status" : code,
            "success" : False,
            "error" : message if message else "Bad Request"
        }
        
    @staticmethod
    def NotFound(message="Resource not found"):
        return {
        "status": Response.HTTP_NOT_FOUND,
        "success": False,
        "error": message
        }

    @staticmethod
    def Unauthorized(message="Unauthorized access"):
        return {
        "status": Response.HTTP_UNAUTHORIZED,
        "success": False,
        "error": message
        }

    @staticmethod
    def ValidationError(errors):
        return {
        "status": Response.HTTP_VALIDATION_ERROR,
        "success": False,
        "error": "Validation error"
        }

    @staticmethod
    def Paginated(data, page, per_page, total):
        return {
        "status": Response.HTTP_OK,
        "success": True,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": -(-total // per_page)
        }
        }

    @staticmethod
    def ServerError(message="Internal server error"):
        return {
        "status": Response.HTTP_SERVER_ERROR,
        "success": False,
        "error": message
        }
        