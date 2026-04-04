import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

/// Low-level HTTP helper that attaches the JWT bearer token.
class ApiService {
  final String _baseUrl = ApiConfig.baseUrl;
  String? _token;

  void setToken(String? token) => _token = token;
  String? get token => _token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<Map<String, dynamic>> get(String path,
      {Map<String, String>? query}) async {
    final uri = Uri.parse('$_baseUrl$path')
        .replace(queryParameters: query);
    final response = await http.get(uri, headers: _headers);
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  Future<List<dynamic>> getList(String path,
      {Map<String, String>? query}) async {
    final uri = Uri.parse('$_baseUrl$path')
        .replace(queryParameters: query);
    final response = await http.get(uri, headers: _headers);
    _assertOk(response);
    return jsonDecode(response.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> post(String path,
      {Map<String, dynamic>? body}) async {
    final response = await http.post(
      Uri.parse('$_baseUrl$path'),
      headers: _headers,
      body: body != null ? jsonEncode(body) : null,
    );
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  Future<Map<String, dynamic>> patch(String path,
      {Map<String, dynamic>? body}) async {
    final response = await http.patch(
      Uri.parse('$_baseUrl$path'),
      headers: _headers,
      body: body != null ? jsonEncode(body) : null,
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
    final uri = Uri.parse('$_baseUrl$path');
    final request = http.MultipartRequest('POST', uri);
    if (_token != null) {
      request.headers['Authorization'] = 'Bearer $_token';
    }
    request.files.add(await http.MultipartFile.fromPath(fieldName, filePath));
    if (fields != null) {
      request.fields.addAll(fields);
    }
    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    _assertOk(response);
    if (response.body.isEmpty) return {};
    final decoded = jsonDecode(response.body);
    return decoded is Map<String, dynamic> ? decoded : {};
  }

  /// Open an SSE stream and yield raw lines.
  Stream<String> sseStream(String path) async* {
    final request =
        http.Request('GET', Uri.parse('$_baseUrl$path'));
    request.headers.addAll(_headers);
    request.headers['Accept'] = 'text/event-stream';
    request.headers['Cache-Control'] = 'no-cache';

    final streamedResponse = await http.Client().send(request);
    if (streamedResponse.statusCode != 200) {
      throw Exception('SSE connection failed: ${streamedResponse.statusCode}');
    }

    await for (final chunk
        in streamedResponse.stream.transform(utf8.decoder)) {
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
}

class ApiException implements Exception {
  final int statusCode;
  final String body;
  const ApiException(this.statusCode, this.body);

  @override
  String toString() => 'ApiException($statusCode): $body';
}
