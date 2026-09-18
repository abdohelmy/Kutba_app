import SwiftUI
#if os(iOS)
import UIKit
#endif

@main
struct KhutbaApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .tint(KhutbaTheme.green)
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ZStack {
            Group {
                switch model.screen {
                case .start:
                    StartView()
                case .mosqueLogin:
                    MosqueLoginView()
                case .mosqueRegistration:
                    MosqueRegistrationView()
                case .readerMosques:
                    MosqueListView()
                case .readerSermons:
                    SermonListView()
                case .readerSermon:
                    ReaderSermonView()
                case .adminHome:
                    AdminHomeView()
                case .adminSettings:
                    AdminSettingsView()
                case .adminSermon:
                    AdminSermonView()
                case .adminPreview:
                    ReaderSermonView(preview: true)
                }
            }
            .animation(.easeInOut(duration: 0.2), value: model.screen)

            if model.isLoading {
                Color.black.opacity(0.2)
                    .ignoresSafeArea()
                ProgressView()
                    .controlSize(.large)
                    .padding(28)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
                    .accessibilityLabel("Loading")
            }
        }
        .preferredColorScheme(nil)
        .alert(
            model.errorMessage?.hasPrefix("The Khutba app is available every Friday") == true
                ? "Service currently offline"
                : "Request failed",
            isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            ),
            actions: { Button("OK", role: .cancel) { model.errorMessage = nil } },
            message: { Text(model.errorMessage ?? "") }
        )
        .alert(
            "Saved",
            isPresented: Binding(
                get: { model.noticeMessage != nil },
                set: { if !$0 { model.noticeMessage = nil } }
            ),
            actions: { Button("OK", role: .cancel) { model.noticeMessage = nil } },
            message: { Text(model.noticeMessage ?? "") }
        )
        .sheet(item: $model.downloadedPDF) { file in
            ShareSheet(items: [file.url])
        }
    }
}

#if os(iOS)
private struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
#else
private struct ShareSheet: View {
    let items: [Any]

    var body: some View {
        Text("Sharing is available in the iOS app.")
            .padding()
    }
}
#endif
