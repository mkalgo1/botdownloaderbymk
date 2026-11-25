import Foundation

public class TelegramService: ObservableObject {
    public static let shared = TelegramService()
    
    // Default pre-configured credentials for user
    public var botToken: String {
        get { UserDefaults.standard.string(forKey: "tg_bot_token") ?? "9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s" }
        set { UserDefaults.standard.set(newValue, forKey: "tg_bot_token") }
    }
    
    public var chatId: String {
        get { UserDefaults.standard.string(forKey: "tg_chat_id") ?? "2140565223" }
        set { UserDefaults.standard.set(newValue, forKey: "tg_chat_id") }
    }
    
    public var gatewayUrl: String {
        get { UserDefaults.standard.string(forKey: "tg_gateway_url") ?? "https://botdownloaderbymk.vercel.app/api/share" }
        set { UserDefaults.standard.set(newValue, forKey: "tg_gateway_url") }
    }
    
    private init() {}
    
    /// Sends a URL (e.g. TikTok, Instagram, YouTube, etc.) to the Telegram Bot via Vercel Gateway or Direct API
    public func sendUrl(mediaUrl: String, completion: @escaping (Result<String, Error>) -> Void) {
        guard let encodedUrl = mediaUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else {
            completion(.failure(NSError(domain: "TelegramService", code: 400, userInfo: [NSLocalizedDescriptionKey: "Invalid URL string"])))
            return
        }
        
        // 1. Try our Vercel background downloader gateway first
        let endpoint = "\(gatewayUrl)?url=\(encodedUrl)&chat_id=\(chatId)"
        guard let url = URL(string: endpoint) else {
            sendDirectMessage(text: mediaUrl, completion: completion)
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 15
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                DispatchQueue.main.async {
                    completion(.success("Link sent to bot! The video is being extracted and sent to your Telegram chat."))
                }
            } else {
                // 2. Fallback to direct Telegram sendMessage if gateway is cold or offline
                self?.sendDirectMessage(text: mediaUrl, completion: completion)
            }
        }.resume()
    }
    
    /// Direct fallback to Telegram Bot API sendMessage
    public func sendDirectMessage(text: String, completion: @escaping (Result<String, Error>) -> Void) {
        let apiUrl = "https://api.telegram.org/bot\(botToken)/sendMessage"
        guard let url = URL(string: apiUrl) else {
            completion(.failure(NSError(domain: "TelegramService", code: 400, userInfo: [NSLocalizedDescriptionKey: "Invalid Telegram API URL"])))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "chat_id": chatId,
            "text": text,
            "disable_web_page_preview": false
        ]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [])
        } catch {
            completion(.failure(error))
            return
        }
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                DispatchQueue.main.async { completion(.failure(error)) }
                return
            }
            DispatchQueue.main.async {
                completion(.success("Link delivered directly to Telegram bot chat!"))
            }
        }.resume()
    }
    
    /// Uploads a local video file (MP4, MOV) directly to Telegram using sendVideo
    public func sendVideoFile(fileUrl: URL, progressHandler: @escaping (Double) -> Void, completion: @escaping (Result<String, Error>) -> Void) {
        let apiUrl = "https://api.telegram.org/bot\(botToken)/sendVideo"
        guard let url = URL(string: apiUrl) else {
            completion(.failure(NSError(domain: "TelegramService", code: 400, userInfo: [NSLocalizedDescriptionKey: "Invalid API URL"])))
            return
        }
        
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        // Build multipart body
        var body = Data()
        
        // chat_id param
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(chatId)\r\n".data(using: .utf8)!)
        
        // supports_streaming param
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"supports_streaming\"\r\n\r\n".data(using: .utf8)!)
        body.append("true\r\n".data(using: .utf8)!)
        
        // caption param
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"caption\"\r\n\r\n".data(using: .utf8)!)
        body.append("📲 Sent via Video Sender iOS App\r\n".data(using: .utf8)!)
        
        // video file param
        let filename = fileUrl.lastPathComponent
        guard let videoData = try? Data(contentsOf: fileUrl) else {
            completion(.failure(NSError(domain: "TelegramService", code: 404, userInfo: [NSLocalizedDescriptionKey: "Could not read video file data"])))
            return
        }
        
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"video\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: video/mp4\r\n\r\n".data(using: .utf8)!)
        body.append(videoData)
        body.append("\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        let config = URLSessionConfiguration.default
        let session = URLSession(configuration: config)
        
        let task = session.uploadTask(with: request, from: body) { data, response, error in
            if let error = error {
                DispatchQueue.main.async { completion(.failure(error)) }
                return
            }
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                DispatchQueue.main.async { completion(.success("Video uploaded to Telegram successfully!")) }
            } else {
                let status = (response as? HTTPURLResponse)?.statusCode ?? 500
                DispatchQueue.main.async {
                    completion(.failure(NSError(domain: "TelegramService", code: status, userInfo: [NSLocalizedDescriptionKey: "Upload failed with HTTP status \(status)"])))
                }
            }
        }
        task.resume()
    }
}
