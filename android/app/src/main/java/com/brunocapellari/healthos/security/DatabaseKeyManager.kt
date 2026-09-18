package com.brunocapellari.healthos.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class DatabaseKeyManager(private val context: Context) {
    private val alias = "healthos_database_wrap_v1"
    private val preferences = context.getSharedPreferences("healthos_keystore_state", Context.MODE_PRIVATE)
    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun databasePassphrase(): ByteArray {
        ensureWrappingKey()
        val encoded = preferences.getString("wrapped_db_key", null)
        if (encoded == null) {
            val passphrase = ByteArray(32).also(SecureRandom()::nextBytes)
            preferences.edit().putString("wrapped_db_key", wrap(passphrase)).apply()
            return passphrase
        }
        return unwrap(encoded)
    }

    private fun ensureWrappingKey() {
        if (keyStore.containsAlias(alias)) return
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        generator.generateKey()
    }

    private fun wrappingKey(): SecretKey = keyStore.getKey(alias, null) as SecretKey

    private fun wrap(clear: ByteArray): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey())
        val payload = cipher.iv + cipher.doFinal(clear)
        return Base64.encodeToString(payload, Base64.NO_WRAP)
    }

    private fun unwrap(encoded: String): ByteArray {
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        require(payload.size > 12) { "Wrapped database key is corrupt" }
        val nonce = payload.copyOfRange(0, 12)
        val ciphertext = payload.copyOfRange(12, payload.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, wrappingKey(), GCMParameterSpec(128, nonce))
        return cipher.doFinal(ciphertext)
    }
}
