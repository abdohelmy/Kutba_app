import SwiftUI

struct StartView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(spacing: 30) {
                VStack(spacing: 14) {
                    ZStack {
                        Circle()
                            .fill(.white.opacity(0.16))
                            .frame(width: 76, height: 76)
                        Image(systemName: "book.pages.fill")
                            .font(.system(size: 37))
                            .foregroundStyle(.white)
                    }
                    Text("Khutba")
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                    Text("Faithful translations. Reviewed by your mosque.")
                        .font(.title3)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.white.opacity(0.84))
                }
                .padding(.top, 48)

                VStack(alignment: .leading, spacing: 15) {
                    Text("How would you like to continue?")
                        .font(.title2.bold())
                    Text("Readers can enter immediately. Mosque teams sign in to manage khutbas.")
                        .foregroundStyle(.secondary)
                    RoleButton(
                        title: "Individual",
                        description: "Choose a mosque and read reviewed khutbas",
                        systemImage: "person.fill",
                        action: model.continueAsIndividual
                    )
                    RoleButton(
                        title: "Mosque",
                        description: "Upload, review, publish, and remove khutbas",
                        systemImage: "building.columns.fill",
                        action: model.openMosqueLogin
                    )
                }
                .padding(22)
                .background(.background, in: RoundedRectangle(cornerRadius: 30, style: .continuous))
                .shadow(color: .black.opacity(0.13), radius: 18, y: 8)
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 30)
        }
        .background(
            LinearGradient(
                colors: [KhutbaTheme.deepGreen, KhutbaTheme.brightGreen, KhutbaTheme.cream],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }
}

private struct RoleButton: View {
    let title: String
    let description: String
    let systemImage: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 16) {
                Image(systemName: systemImage)
                    .font(.title2)
                    .foregroundStyle(.white)
                    .frame(width: 52, height: 52)
                    .background(KhutbaTheme.green, in: Circle())
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.title3.bold())
                        .foregroundStyle(.primary)
                    Text(description)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(KhutbaTheme.green)
            }
            .padding(17)
            .background(KhutbaTheme.mint.opacity(0.5), in: RoundedRectangle(cornerRadius: 18))
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .stroke(KhutbaTheme.green, lineWidth: 1.5)
            }
        }
        .buttonStyle(.plain)
    }
}

struct MosqueLoginView: View {
    @EnvironmentObject private var model: AppModel
    @State private var username = ""
    @State private var password = ""

    private var usernameIsValid: Bool {
        username.range(of: #"^[A-Za-z0-9._-]{3,64}$"#, options: .regularExpression) != nil
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    SectionHeading(
                        title: "Manage your mosque’s khutbas",
                        subtitle: "Sign in to an existing account or create a new mosque profile."
                    )
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .textFieldStyle(.roundedBorder)
                    Button("Sign in to mosque workspace") {
                        model.login(username: username, password: password)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .frame(maxWidth: .infinity)
                    .disabled(!usernameIsValid || password.isEmpty)
                    Divider()
                    Button("Create a mosque profile", action: model.openMosqueRegistration)
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                }
                .padding(22)
            }
            .khutbaBackground()
            .navigationBarBackButtonHidden()
            .toolbar { ScreenHeader(title: "Mosque sign in", backAction: model.back) }
        }
    }
}

struct MosqueRegistrationView: View {
    @EnvironmentObject private var model: AppModel
    @State private var mosqueName = ""
    @State private var city = ""
    @State private var country = "DK"
    @State private var adminName = ""
    @State private var username = ""
    @State private var password = ""
    @State private var permissionPassword = ""

    private var formIsValid: Bool {
        mosqueName.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 &&
        city.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 &&
        country.range(of: #"^[A-Za-z]{2}$"#, options: .regularExpression) != nil &&
        adminName.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 &&
        username.range(of: #"^[A-Za-z0-9._-]{3,64}$"#, options: .regularExpression) != nil &&
        password.count >= 6 && !permissionPassword.isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("The permission password is required before the profile can be created.")
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Set up your mosque workspace")
                }
                Section("Mosque") {
                    TextField("Mosque name", text: $mosqueName)
                    TextField("City", text: $city)
                    TextField("Country code", text: $country)
                        .textInputAutocapitalization(.characters)
                        .onChange(of: country) { _, value in country = String(value.prefix(2)) }
                    Text("Use two letters, for example DK.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Administrator") {
                    TextField("Administrator name", text: $adminName)
                        .textContentType(.name)
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Account password", text: $password)
                        .textContentType(.newPassword)
                    Text("Use at least 6 characters.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    SecureField("Permission password", text: $permissionPassword)
                }
                Section {
                    Button("Create mosque profile") {
                        model.registerMosque(
                            mosqueName: mosqueName,
                            city: city,
                            country: country,
                            adminName: adminName,
                            username: username,
                            password: password,
                            permissionPassword: permissionPassword
                        )
                    }
                    .frame(maxWidth: .infinity)
                    .disabled(!formIsValid)
                }
            }
            .navigationBarBackButtonHidden()
            .toolbar { ScreenHeader(title: "Create mosque profile", backAction: model.back) }
        }
    }
}
