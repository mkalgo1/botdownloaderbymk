import SwiftUI

@main
struct VideoSenderApp: App {
    @StateObject private var tg = TelegramService.shared
    @State private var bannerText: String = ""
    @State private var showBanner: Bool = false
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .overlay(
                    VStack {
                        if showBanner {
                            HStack {
                                Image(systemName: "paperplane.fill")
                                    .foregroundColor(.white)
                                Text(bannerText)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                    .foregroundColor(.white)
                                Spacer()
                            }
                            .padding()
                            .background(Color.blue)
                            .cornerRadius(12)
                            .shadow(radius: 6)
                            .padding(.horizontal)
                            .transition(.move(edge: .top).combined(with: .opacity))
                        }
                        Spacer()
                    }
                    .animation(.spring(), value: showBanner)
                )
                .onOpenURL { incomingUrl in
                    handleIncomingUrl(incomingUrl)
                }
        }
    }
    
    /// Handles incoming links and shared files passed to the app
    private func handleIncomingUrl(_ url: URL) {
        // 1. Check if it's a file URL (video shared from Photos / Files / other apps)
        if url.isFileURL {
            showToast("Sending shared video to Telegram...")
            
            // Start accessing security scoped resource if needed
            let accessing = url.startAccessingSecurityScopedResource()
            defer {
                if accessing { url.stopAccessingSecurityScopedResource() }
            }
            
            tg.sendVideoFile(fileUrl: url, progressHandler: { _ in }) { result in
                switch result {
                case .success(let msg):
                    showToast("✅ \(msg)")
                case .failure(let err):
                    showToast("❌ Error: \(err.localizedDescription)")
                }
            }
            return
        }
        
        // 2. Check if custom scheme: videosender://send?url=https://...
        if url.scheme == "videosender" {
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let queryItems = components.queryItems {
                if let targetUrl = queryItems.first(where: { $0.name == "url" || $0.name == "text" })?.value {
                    dispatchMediaUrl(targetUrl)
                    return
                }
            }
        }
        
        // 3. Fallback: URL string itself
        dispatchMediaUrl(url.absoluteString)
    }
    
    private func dispatchMediaUrl(_ urlString: String) {
        showToast("Sending link to Telegram bot...")
        tg.sendUrl(mediaUrl: urlString) { result in
            switch result {
            case .success(let msg):
                showToast("✅ \(msg)")
            case .failure(let err):
                showToast("❌ Error: \(err.localizedDescription)")
            }
        }
    }
    
    private func showToast(_ text: String) {
        bannerText = text
        showBanner = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) {
            showBanner = false
        }
    }
}
