// lorem-ipsum-generator.js

const fs = require("fs");
const path = require("path");
const { LoremIpsum } = require("lorem-ipsum");

// --- Configuration ---
const DEFAULT_FILENAME = "generated_lorem_ipsum.txt";
const DEFAULT_SIZE_MB = 1; // Default to 1MB if no size is provided
const BYTE_PER_MB = 1024 * 1024;
const CHUNK_SIZE_BYTES = 64 * 1024; // Write in 64KB chunks for efficiency

// --- Initialize Lorem Ipsum Generator ---
const lorem = new LoremIpsum({
  sentencesPerParagraph: {
    max: 8,
    min: 4,
  },
  wordsPerSentence: {
    max: 16,
    min: 4,
  },
});

/**
 * Parses command line arguments to get filename and desired size.
 * @returns {{filename: string, targetSizeMb: number}}
 */
function parseArguments() {
  const args = process.argv.slice(2);
  let targetSizeMb = DEFAULT_SIZE_MB;
  let filename = DEFAULT_FILENAME;

  if (args.length === 0) {
    console.log(`\nUsage: node ${path.basename(process.argv[1])} <target_size_mb> [output_filename]`);
    console.log(`Example: node ${path.basename(process.argv[1])} 100 my_big_text_file.txt`);
    console.log(`Using default: ${DEFAULT_SIZE_MB}MB to ${DEFAULT_FILENAME}\n`);
  }

  // Parse target size
  if (args[0]) {
    const parsedSize = parseFloat(args[0]);
    if (!isNaN(parsedSize) && parsedSize > 0) {
      targetSizeMb = parsedSize;
    } else {
      console.warn(`Warning: Invalid size '${args[0]}'. Using default size ${DEFAULT_SIZE_MB}MB.`);
    }
  }

  // Parse optional filename
  if (args[1]) {
    filename = args[1];
  }

  return { filename, targetSizeMb };
}

/**
 * Generates a text file with lorem ipsum content until it reaches the target size.
 * @param {string} filename - The name of the file to create.
 * @param {number} targetSizeBytes - The target size of the file in bytes.
 */
async function generateLargeTextFile(filename, targetSizeBytes) {
  console.log(`Attempting to generate file: ${filename}`);
  console.log(`Target size: ${targetSizeBytes / BYTE_PER_MB} MB`);

  let currentBytesWritten = 0;
  let progressPercentage = 0;
  const writeStream = fs.createWriteStream(filename);

  return new Promise((resolve, reject) => {
    writeStream.on("error", (err) => {
      console.error(`Error writing to file: ${err.message}`);
      reject(err);
    });

    writeStream.on("finish", () => {
      console.log(`\nFile generation complete: ${filename}`);
      console.log(`Final size: ${currentBytesWritten / BYTE_PER_MB} MB`);
      resolve();
    });

    // Function to write data in chunks
    const writeData = () => {
      let canWrite = true;
      while (canWrite && currentBytesWritten < targetSizeBytes) {
        // Generate a chunk of lorem ipsum text (e.g., 100 sentences)
        const textChunk = lorem.generateSentences(100) + "\n";
        const chunkByteLength = Buffer.byteLength(textChunk, "utf8");

        // Check if writing this chunk would exceed the target size significantly
        if (currentBytesWritten + chunkByteLength > targetSizeBytes * 1.05 && currentBytesWritten < targetSizeBytes) {
          // If we are close to the target, generate just enough text
          const remainingBytes = targetSizeBytes - currentBytesWritten;
          // Estimate sentences needed based on average sentence length
          const avgSentenceLength = Buffer.byteLength(lorem.generateSentences(1), "utf8");
          const sentencesToGenerate = Math.ceil(remainingBytes / avgSentenceLength) + 1; // +1 to ensure we pass the target
          const finalChunk = lorem.generateSentences(sentencesToGenerate) + "\n";
          const finalChunkAdjusted = finalChunk.substring(0, remainingBytes); // Trim to exact bytes
          currentBytesWritten += Buffer.byteLength(finalChunkAdjusted, "utf8");
          canWrite = writeStream.write(finalChunkAdjusted);
          break; // Exit the loop as we've written the final part
        } else {
          canWrite = writeStream.write(textChunk);
          currentBytesWritten += chunkByteLength;
        }

        // Update and display progress
        const newProgress = Math.floor((currentBytesWritten / targetSizeBytes) * 100);
        if (newProgress !== progressPercentage) {
          progressPercentage = newProgress;
          process.stdout.write(`Progress: ${progressPercentage}% (${(currentBytesWritten / BYTE_PER_MB).toFixed(2)} MB)\r`);
        }
      }

      if (currentBytesWritten < targetSizeBytes) {
        // If writeStream.write returned false, it means the buffer is full.
        // Wait for the 'drain' event before writing more.
        writeStream.once("drain", writeData);
      } else {
        // We've written enough data, close the stream
        writeStream.end();
      }
    };

    writeData(); // Start writing
  });
}

// --- Main Execution ---
(async () => {
  const { filename, targetSizeMb } = parseArguments();
  const targetSizeBytes = targetSizeMb * BYTE_PER_MB;

  try {
    // Ensure the output directory exists
    const dir = path.dirname(filename);
    if (dir && dir !== ".") {
      // Check if 'dir' is not empty or current directory
      await fs.promises.mkdir(dir, { recursive: true });
    }

    // Check if file already exists and warn the user
    if (fs.existsSync(filename)) {
      console.warn(`Warning: File '${filename}' already exists. It will be overwritten.`);
    }

    await generateLargeTextFile(filename, targetSizeBytes);
    console.log(`\nSuccessfully created ${filename} with approximately ${targetSizeMb} MB of content.`);
  } catch (error) {
    console.error(`\nFailed to generate file: ${error.message}`);
    process.exit(1);
  }
})();
