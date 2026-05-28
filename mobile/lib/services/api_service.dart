import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

/// Low-level HTTP helper that attaches the JWT bearer token.
class ApiService {
  final String _baseUrl = ApiConfig.baseUrl;
  final http.Client _client;
  String? _token;
  Future<bool> Function()? _refreshAuth;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  void setToken(String? token) => _token = token;
  String? get token => _token;
  void setAuthRefreshHandler(Future<bool> Function()? handler) =>
      _refreshAuth = handler;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<Map<String, dynamic>> get(String path,
      {Map<String, String>? query}) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: query);
    final response = await _sendWithAuthRetry(
      path,
      () => _client.get(uri, headers: _headers),
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  Future<List<dynamic>> getList(String path,
      {Map<String, String>? query}) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: query);
    final response = await _sendWithAuthRetry(
      path,
      () => _client.get(uri, headers: _headers),
    );
    _assertOk(response);
    return jsonDecode(response.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> post(String path,
      {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final response = await _sendWithAuthRetry(
      path,
      () => _client.post(
        uri,
        headers: _headers,
        body: body != null ? jsonEncode(body) : null,
      ),
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  Future<Map<String, dynamic>> patch(String path,
      {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final response = await _sendWithAuthRetry(
      path,
      () => _client.patch(
        uri,
        headers: _headers,
        body: body != null ? jsonEncode(body) : null,
      ),
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  Future<Map<String, dynamic>> put(String path,
      {Map<String, dynamic>? body}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final response = await _sendWithAuthRetry(
      path,
      () => _client.put(
        uri,
        headers: _headers,
        body: body != null ? jsonEncode(body) : null,
      ),
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  /// Upload a file via multipart/form-data POST.
  Future<Map<String, dynamic>> uploadFile(
    String path, {
    required String filePath,
    String fieldName = 'file',
    Map<String, String>? fields,
  }) async {
    Future<http.Response> send() async {
      final uri = Uri.parse('$_baseUrl$path');
      final request = http.MultipartRequest('POST', uri);
      if (_token != null) {
        request.headers['Authorization'] = 'Bearer $_token';
      }
      request.files.add(await http.MultipartFile.fromPath(fieldName, filePath));
      if (fields != null) {
        request.fields.addAll(fields);
      }
      final streamedResponse = await _client.send(request);
      return http.Response.fromStream(streamedResponse);
    }

    final response = await _sendWithAuthRetry(
      path,
      send,
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  /// Open an SSE stream and yield raw lines.
  Stream<String> sseStream(String path) async* {
    final request = http.Request('GET', Uri.parse('$_baseUrl$path'));
    request.headers.addAll(_headers);
    request.headers['Accept'] = 'text/event-stream';
    request.headers['Cache-Control'] = 'no-cache';

    final streamedResponse = await http.Client().send(request);
    if (streamedResponse.statusCode != 200) {
      throw Exception('SSE connection failed: ${streamedResponse.statusCode}');
    }

    await for (final chunk in streamedResponse.stream.transform(utf8.decoder)) {
      for (final line in chunk.split('\n')) {
        if (line.isNotEmpty) yield line;
      }
    }
  }

  void _assertOk(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.statusCode, response.body);
    }
  }

  Future<http.Response> _sendWithAuthRetry(
    String path,
    Future<http.Response> Function() send,
  ) async {
    final response = await send();
    if (response.statusCode != 401 ||
        _token == null ||
        _refreshAuth == null ||
        path == ApiConfig.loginPath ||
        path == ApiConfig.registerPath ||
        path == ApiConfig.googleAuthPath ||
        path == ApiConfig.refreshPath) {
      return response;
    }

    final refreshed = await _refreshAuth!();
    if (!refreshed || _token == null) return response;
    return send();
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String body;
  const ApiException(this.statusCode, this.body);

  @override
  String toString() => 'ApiException($statusCode): $body';
}
