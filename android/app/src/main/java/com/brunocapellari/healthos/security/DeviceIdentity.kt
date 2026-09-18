package com.brunocapellari.healthos.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.ECGenParameterSpec

class DeviceIdentity {
    private val alias = "healthos_device_signing_v1"
    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun ensureKey(): Unit {
        if (keyStore.containsAlias(alias)) return
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        val spec = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(false)
            .build()
        generator.initialize(spec)
        generator.generateKeyPair()
    }

    fun deviceId(): String {
        ensureKey()
        val encoded = keyStore.getCertificate(alias).publicKey.encoded
        return MessageDigest.getInstance("SHA-256")
            .digest(encoded)
            .joinToString("") { "%02x".format(it) }
    }

    fun publicKeyPem(): String {
        ensureKey()
        val encoded = keyStore.getCertificate(alias).publicKey.encoded
        val base64 = Base64.encodeToString(encoded, Base64.NO_WRAP)
        return buildString {
            appendLine("-----BEGIN PUBLIC KEY-----")
            base64.chunked(64).forEach(::appendLine)
            append("-----END PUBLIC KEY-----")
        }
    }

    fun signBase64(message: String): String {
        ensureKey()
        val privateKey = keyStore.getKey(alias, null)
        val signer = Signature.getInstance("SHA256withECDSA")
        signer.initSign(privateKey as java.security.PrivateKey)
        signer.update(message.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(signer.sign(), Base64.NO_WRAP)
    }
}
