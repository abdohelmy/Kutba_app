-keepattributes *Annotation*
-keepclassmembers class kotlinx.serialization.** { *; }

# Retrofit discovers this suspend return type through reflection. The repository ignores
# the response body, so R8 otherwise removes the DTO and its generated serializer.
-keep class com.khutba.app.model.TranslationQueued** { *; }
