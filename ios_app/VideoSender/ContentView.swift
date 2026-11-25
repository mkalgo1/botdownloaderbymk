import SwiftUI
import PhotosUI

struct ContentView: View {
    @ObservedObject var tg = TelegramService.shared
    
    @State private var inputUrl: String = ""
    @State private var statusMessage: String = ""
    @State private var isSuccess: Bool = false
    @State private var isLoading: Bool = false
    @State private var showSettings: Bool = false
    @State private var selectedPhotoItem: PhotosPickerItem? = nil
    
    var body: some View {
        NavigationView {
            ZStack {
                Color(UIColor.systemGroupedBackground)
                    .ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 20) {
                        // Header Card
                        VStack(spacing: 8) {
                            Image(systemName: "paperplane.circle.fill")
                                .resizable()
                                .frame(width: 64, height: 64)
                                .foregroundColor(.blue)
                            
                            Text("Telegram Video Sender")
                                .font(.title2)
                                .fontWeight(.bold)
                            
                            HStack(spacing: 6) {
                                Circle()
                                    .fill(Color.green)
                                    .frame(width: 8, height: 8)
                                Text("Bot Connected: @vidsmkdownloaderbot")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.top, 10)
                        
                        // Status Banner
                        if !statusMessage.isEmpty {
                            HStack {
                                Image(systemName: isSuccess ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                    .foregroundColor(isSuccess ? .green : .red)
                                Text(statusMessage)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                    .foregroundColor(isSuccess ? .green : .red)
                                Spacer()
                            }
                            .padding()
                            .background(isSuccess ? Color.green.opacity(0.12) : Color.red.opacity(0.12))
                            .cornerRadius(12)
                            .padding(.horizontal)
                        }
                        
                        // Action Box: Paste URL
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Quick Link Dispatch")
                                .font(.headline)
                            
                            HStack {
                                Image(systemName: "link")
                                    .foregroundColor(.secondary)
                                TextField("Paste TikTok, Instagram, Pinterest URL...", text: $inputUrl)
                                    .textFieldStyle(PlainTextFieldStyle())
                                    .autocapitalization(.none)
                                    .disableAutocorrection(true)
                                
                                if !inputUrl.isEmpty {
                                    Button(action: { inputUrl = "" }) {
                                        Image(systemName: "xmark.circle.fill")
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding()
                            .background(Color(UIColor.secondarySystemGroupedBackground))
                            .cornerRadius(10)
                            
                            Button(action: sendCurrentUrl) {
                                HStack {
                                    if isLoading {
                                        ProgressView()
                                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                            .padding(.trailing, 4)
                                    }
                                    Image(systemName: "arrow.up.circle.fill")
                                    Text("Send to Telegram Bot")
                                        .fontWeight(.semibold)
                                }
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(inputUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? Color.gray.opacity(0.5) : Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(12)
                            }
                            .disabled(inputUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
                        }
                        .padding()
                        .background(Color(UIColor.secondarySystemGroupedBackground))
                        .cornerRadius(16)
                        .padding(.horizontal)
                        
                        // Action Box: Pick Video From Gallery
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Share from Photos")
                                .font(.headline)
                            
                            PhotosPicker(selection: $selectedPhotoItem, matching: .videos) {
                                HStack {
                                    Image(systemName: "photo.on.rectangle.angled")
                                    Text("Select Video from Gallery")
                                        .fontWeight(.medium)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .foregroundColor(.secondary)
                                }
                                .padding()
                                .background(Color(UIColor.systemBackground))
                                .cornerRadius(10)
                            }
                            .onChange(of: selectedPhotoItem) { newItem in
                                handleSelectedVideo(newItem)
                            }
                        }
                        .padding()
                        .background(Color(UIColor.secondarySystemGroupedBackground))
                        .cornerRadius(16)
                        .padding(.horizontal)
                        
                        // Share Sheet Guide Card
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Image(systemName: "square.and.arrow.up")
                                    .foregroundColor(.blue)
                                Text("How to Share from Any App")
                                    .font(.headline)
                            }
                            
                            VStack(alignment: .leading, spacing: 8) {
                                GuideStep(num: "1", text: "In TikTok, Instagram, YouTube, or Photos, tap the Share icon.")
                                GuideStep(num: "2", text: "In the apps row, scroll right and tap 'Video Sender' (or tap 'More' and add it).")
                                GuideStep(num: "3", text: "That's it! The video link or file is automatically routed to your Telegram bot.")
                            }
                        }
                        .padding()
                        .background(Color(UIColor.secondarySystemGroupedBackground))
                        .cornerRadius(16)
                        .padding(.horizontal)
                        
                        Spacer(minLength: 30)
                    }
                }
            }
            .navigationTitle("Sender")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showSettings.toggle() }) {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView(tg: tg)
            }
        }
    }
    
    private func sendCurrentUrl() {
        let clean = inputUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        
        isLoading = true
        statusMessage = "Sending to Telegram bot..."
        isSuccess = true
        
        tg.sendUrl(mediaUrl: clean) { result in
            isLoading = false
            switch result {
            case .success(let msg):
                statusMessage = msg
                isSuccess = true
                inputUrl = ""
            case .failure(let err):
                statusMessage = err.localizedDescription
                isSuccess = false
            }
        }
    }
    
    private func handleSelectedVideo(_ item: PhotosPickerItem?) {
        guard let item = item else { return }
        isLoading = true
        statusMessage = "Loading video from library..."
        isSuccess = true
        
        item.loadTransferable(type: MovieTransferable.self) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let movie?):
                    statusMessage = "Uploading video to Telegram bot..."
                    tg.sendVideoFile(fileUrl: movie.url, progressHandler: { _ in }) { uploadResult in
                        isLoading = false
                        switch uploadResult {
                        case .success(let msg):
                            statusMessage = msg
                            isSuccess = true
                        case .failure(let err):
                            statusMessage = err.localizedDescription
                            isSuccess = false
                        }
                    }
                case .success(.none):
                    isLoading = false
                    statusMessage = "Could not load video"
                    isSuccess = false
                case .failure(let err):
                    isLoading = false
                    statusMessage = err.localizedDescription
                    isSuccess = false
                }
            }
        }
    }
}

struct GuideStep: View {
    let num: String
    let text: String
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(num)
                .font(.caption)
                .fontWeight(.bold)
                .foregroundColor(.white)
                .frame(width: 20, height: 20)
                .background(Circle().fill(Color.blue))
            Text(text)
                .font(.footnote)
                .foregroundColor(.secondary)
        }
    }
}

struct SettingsView: View {
    @ObservedObject var tg: TelegramService
    @Environment(\.dismiss) var dismiss
    
    @State private var token: String = ""
    @State private var chat: String = ""
    @State private var gateway: String = ""
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Telegram Bot Credentials")) {
                    SecureField("Bot Token", text: $token)
                    TextField("Chat ID", text: $chat)
                }
                
                Section(header: Text("Vercel Gateway")) {
                    TextField("Gateway URL", text: $gateway)
                }
                
                Section(footer: Text("Defaults are configured for @vidsmkdownloaderbot and your chat ID.")) {
                    Button("Reset to Defaults") {
                        token = "9134223706:AAGW202tOsHstyIxIUOdyjkRKdflccs8S6s"
                        chat = "2140565223"
                        gateway = "https://botdownloaderbymk.vercel.app/api/share"
                    }
                    .foregroundColor(.red)
                }
            }
            .navigationTitle("Settings")
            .navigationBarItems(
                leading: Button("Cancel") { dismiss() },
                trailing: Button("Save") {
                    tg.botToken = token
                    tg.chatId = chat
                    tg.gatewayUrl = gateway
                    dismiss()
                }
            )
            .onAppear {
                token = tg.botToken
                chat = tg.chatId
                gateway = tg.gatewayUrl
            }
        }
    }
}

// Transferable helper for PhotosPicker
struct MovieTransferable: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let tempDir = FileManager.default.temporaryDirectory
            let target = tempDir.appendingPathComponent("\(UUID().uuidString).mp4")
            try? FileManager.default.removeItem(at: target)
            try FileManager.default.copyItem(at: received.file, to: target)
            return MovieTransferable(url: target)
        }
    }
}
