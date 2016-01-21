from sys import argv
from math import ceil
from telnetlib import Telnet
from optparse import OptionParser, OptionGroup
from progressbar import ProgressBar
import re

TIMEOUT = 2
BLOCK_SIZE = 8192

class BrcmFirmwareDump:
	
	def __init__(self, ip, user, password, port=23):
		
		# Connect 
		self.tn = Telnet(ip,port,TIMEOUT)
		self.tn.set_debuglevel(1)
		# workarround to avoid the connection getting stuck at option negociation
		self.tn.set_option_negotiation_callback(self.option_negociation)
		
		# Some old broadcom versions need any character
		# being send before prompting for the username
		while True:
			r = self.tn.read_until("ogin: ", TIMEOUT)
			if re.search("ogin:", r):
				break
			# Send a '\n'
			self.tn.write("\n")
		
		# Send the username
		self.tn.write(user+"\n")

		# Send the password
		self.tn.read_until("assword: ")
		self.tn.write(password+"\n")
		
		# Get the first prompt
		r = self.tn.read_until("> ")
		
		# Log in as root if necessary
		if re.search("Console", r):
			self.tn.write("su\n")
			self.tn.read_until("assword:  () []")
			self.tn.write("brcm\n")
			self.tn.read_until("> ")
			self.tn.write("\n")
			self.tn.read_until("> ")
				
		self.tn.write("cd flash\n")
		self.tn.read_until("\r\n\r\nCM/Flash> ")
		
		'''
		self.tn.write("deinit\n")
		self.tn.read_until("\r\n\r\nCM/Flash> ")
		
		self.tn.write("init\n")
		self.tn.read_until("\r\n\r\nCM/Flash> ")
		'''
	
	def log(self, message, image=1):
		print "Image%d> %s" % (image, message)
	
	def option_negociation(self, socket, command, option):
		pass
	
	def read_block(self, image, block):

		# Get a read command valid response
		while True:
			offset = block*BLOCK_SIZE
			command = "read 4 %d %d" % (BLOCK_SIZE,offset)
			self.tn.write(command + "\n")
			e = self.tn.read_until("\r\n\r\nCM/Flash> ")
			lines = e.split("\r\n")

			if len(lines)==7:
				response = lines[4].strip().replace(" ", "")
				until = len(response) / 2
				octecs_as_strings = [ response[2*i:2*i+2] for i in range(0,until)]
				
				if len(octecs_as_strings) != BLOCK_SIZE:
					# Continue to try again
					continue
				
				break
				
		return octecs_as_strings
	
	
	def process_block0(self, octecs_as_strings):
		filename = "".join( \
				[ c for c in \
					map(lambda e: e.decode("hex"), octecs_as_strings[20:83]) \
					if c != '\x00'])
		payload_size_hex = "".join(octecs_as_strings[13:16])
		payload_size = int(payload_size_hex,16)
		total_size = int(payload_size_hex,16) + int("0x5c",16)
		
		return filename, total_size
		
	def write_block(self, file, octecs_as_strings):
		as_decimals = map(lambda e: int(e,16), octecs_as_strings)
		file.write(bytearray(as_decimals))
		
	def open_image(self, image):
		self.tn.write("open image%d\n" % image)
		self.tn.read_until("\r\n\r\nCM/Flash> ")
	
	def close_image(self):
		self.tn.write("close\n")
		self.tn.read_until("\r\n\r\nCM/Flash> ")
		
	def download_image(self, image=1):
		
		self.log("Downloading first block...", image)
		self.open_image(image)

		# Read block 0
		octecs_as_strings = self.read_block(image, 0)
		filename, total_size = self.process_block0(octecs_as_strings)
		self.log("Detected firmware '%s' (%d bytes)" % (filename, total_size), image)
		
		# Ask the user whether the fw has to be downloaded
		while True:
			download = raw_input('Do you want to download the firmware? (y/n): ')
			if download.lower() == "n":
				self.close_image()
				return
			elif download.lower() == "y":
				break
		
		total_blocks = int(ceil(total_size / float(BLOCK_SIZE)))
		self.log("Reading next %d blocks (%d bytes each)" % (total_blocks-1, BLOCK_SIZE), image)
		
		readed = BLOCK_SIZE

		# Create ouput filen and save first block
		f = open(filename, "wb")
		self.write_block(f, octecs_as_strings)
						
		# Read the reamaining blocks
		bar = ProgressBar()
		for block in bar(range(1, total_blocks)):
		
			octecs_as_strings = self.read_block(image, block)
			
			# Check if it is the final block
			if (readed + BLOCK_SIZE) > total_size:
				octecs_as_strings = octecs_as_strings[0:total_size-readed]
			
			# Write block to file
			self.write_block(f, octecs_as_strings)
			
			# Update the control counters
			readed += len(octecs_as_strings)
			
		# Close the output file
		f.close()
		
		# Close the flash image zone 
		self.close_image()
		
	def close(self):
		self.tn.write("cd ..\n")
		self.tn.read_until("\r\n\r\nCM> ")
		self.tn.write("exit\n")
		self.tn.close()

def parse_cmdline(argv):
	"""Parses the command-line."""
	
	parser = OptionParser(description='brcm_firmware_dump - telnet dump of firmware images from Broadcom based cable modems.')
	parser.add_option("-i", "--ip", dest="ip", help="Cable Modem IP Address (required)")
	parser.add_option("-u", "--user", dest="user", help="Telnet username")
	parser.add_option("-p", "--password", dest="password", help="Telnet password")
	
	# Parse the user input		  
	(options, args) = parser.parse_args()
	
	# Check required arguments
	if options.ip is None:
		parser.print_help()
		parser.error("Cable modem IP address is required.")
	
	if options.user is None:
		parser.print_help()
		parser.error("Telnet username is required.")
	
	if options.password is None:
		parser.print_help()
		parser.error("Telnet password is required.")
	
	return (options, args)
	
if __name__ == '__main__':
	
	# parse the command line
	options, args = parse_cmdline(argv)
	
	brcm_fw_dump = BrcmFirmwareDump(options.ip, options.user, options.password)
	brcm_fw_dump.download_image(1)
	brcm_fw_dump.download_image(2)
	brcm_fw_dump.close()