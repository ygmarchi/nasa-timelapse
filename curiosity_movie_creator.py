from html.parser import HTMLParser
from subprocess import call
import os
import re
import sys
import urllib
import urllib.request

class curiosity_movie_creator (HTMLParser):
	camera = None
	sub_cameras = [];
	start_sol = 0
	end_sol = None
	download_page = False	
	image_frames = 10
	
	url_template = 'http://mars.jpl.nasa.gov/msl/multimedia/raw/?s=%d&camera=%s'
	image_url_pattern = re.compile ('.*/(([a-zA-Z]+)?_?\w+.JPG)', re.IGNORECASE)
	thumbnails_pattern = re.compile ('\s*THUMBNAIL\s+Data\s+Product\s*')
	
	depth = None
	thumbnails = False
	
	def run (self):	
		#proxy_support = urllib.request.ProxyHandler({'http' : 'http://172.16.20.100:8080'})	
		#opener = urllib.request.build_opener(proxy_support)
		#urllib.request.install_opener(opener)

		sub_camera_len = len (self.sub_cameras)
		if sub_camera_len == 0:
			self.mkdirs ()				
			for sol in range (self.start_sol, self.end_sol + 1):		
				self.reset ()
				
				url = self.url_template % (sol,self.camera);
				print ('Downloading from %s' % url)
				if not self.download_page:
					url_request = urllib.request.urlopen(url)
					self.feed (url_request.read().decode('utf-8'))		
				else:
					file_name = 'sol_%d.html' % sol
					path_name = '%s/%s' % (self.camera, file_name)
					urllib.request.urlretrieve (url, path_name)						
					print ('Retrieved page %s' % path_name)
					
		for sub_camera in self.sub_cameras:
			self.blend (sub_camera, sub_camera_len)

	def reset (self):
		super(curiosity_movie_creator, self).reset()
		self.depth = 0
		self.thumbnails = False
				
	def mkdirs (self, sub_camera = None):
		try:
			os.mkdir (self.camera)
		except FileExistsError:
			pass
			
		if sub_camera is not None:
			try:
				os.mkdir ('%s/%s' % (self.camera, sub_camera))
			except FileExistsError:
				pass	
	
	def handle_starttag(self, tag, attrs):
		if not self.thumbnails:
			if tag == 'div':
				for attr in attrs:
					if attr [0] == 'class' and attr [1] == 'RawImageUTC':
						self.depth = 1
						return
			elif self.depth > 0 and tag == 'a':
				for attr in attrs:
					if attr [0] == 'href':
						image_url = attr [1]	
						match = self.image_url_pattern.match (image_url)
						if match is not None: 
							file_name = match.group (1)
							sub_camera = match.group (2)
							if sub_camera is None:
								sub_camera = 'CAM'
							if not sub_camera in self.sub_cameras:
								self.sub_cameras.append (sub_camera)
							self.mkdirs (sub_camera)
							path_name = '%s/%s/%s' % (self.camera, sub_camera, file_name)
							urllib.request.urlretrieve (image_url, path_name)						
							print ('Retrieved image %s' % file_name)
						else:
							print ('WARN: ignored image %s' % image_url)
					
						
			if self.depth > 0:
				self.depth = self.depth + 1


	def handle_endtag(self, tag):
		if not self.thumbnails:
			if self.depth > 0:
				self.depth = self.depth - 1
			
	def handle_data(self, data):
		if not self.thumbnails:
			self.thumbnails = self.thumbnails_pattern.match (data)

	def blend (self, sub_camera, initial_sub_camera_len):
		if (sys.argv [0] != 'blender'):
			command_start = ['blender', '-b', '-P', sys.argv[0], '--']
			command_middle = ['-C', sub_camera] if initial_sub_camera_len == 0 else []
			command_end = sys.argv [1:]
			blender_command = command_start + command_middle + command_end					
			print ('Calling %s', blender_command)
			call (blender_command)
		else:
			self.do_blend (sub_camera)

	def do_blend (self, sub_camera):
		import bpy
				
		scene = bpy.data.scenes["Scene"]	
		screen = bpy.data.screens['Video Editing']		
		for area in screen.areas:
			if area.type == 'SEQUENCE_EDITOR':
				break
		context = {
			'window': bpy.context.window,
			'scene': scene,
			'screen': screen,
			'area': area,
		}

		in_dir = "%s/%s/%s" % (os.getcwd(), self.camera, sub_camera)
		out_dir = in_dir + ".avi"

		resolution = 1024
		scene.render.resolution_x = resolution
		scene.render.resolution_y = resolution 
		scene.render.resolution_percentage = 100

		# Filter file list by valid file types.
		frame_start = 0
		frame_increment = self.image_frames
		overlap = 4
		lst = sorted (os.listdir(in_dir))
		print ('Sequencing %d images' % len (lst))
		for i in range (len (lst)):
			item = lst [i]
			fileName, fileExtension = os.path.splitext(item)
			if fileExtension.upper () == ".JPG":	
				channel = 1 if i % 2 == 0 else 3
				frame_end = frame_start + frame_increment
				print ('adding image %s, channel %d, frame range (%d, %d)' % (item, channel, frame_start + 1, frame_end))
				bpy.ops.sequencer.image_strip_add(context,
					directory = in_dir, 
					files = [{'name': item}], 
					channel = channel, 
					frame_start = frame_start + 1, 
					frame_end = frame_end, 
					replace_sel = True,
					filemode = 9, 
					filter_image = True, 
					display_type = 'FILE_DEFAULTDISPLAY')
				if i > 0:
					bpy.ops.sequencer.select_grouped(type = 'OVERLAP')
					channel = 2
					print ('adding cross, channel %d, frame range (%d, %d)' % (channel, frame_start, frame_start + overlap))
					bpy.ops.sequencer.effect_strip_add (context,
						type = 'CROSS',
						channel = channel, 
						frame_start = frame_start, 
						frame_end = frame_start + overlap,
						replace_sel = False
					)					
				frame_start = frame_end - overlap

		bpy.data.scenes["Scene"].frame_end = frame_start
		bpy.data.scenes["Scene"].render.image_settings.file_format = 'FFMPEG' 
		bpy.data.scenes["Scene"].render.ffmpeg.format = 'XVID' 
		bpy.data.scenes["Scene"].render.image_settings.compression = 100
		bpy.data.scenes["Scene"].render.filepath = out_dir 
		bpy.ops.render.render( animation=True ) 
	
		project = '%s.blend' % in_dir
		try:
			os.remove (project)
		except FileNotFoundError:
			pass
		bpy.ops.wm.save_as_mainfile (context, filepath = project, check_existing = False)
		

def usage ():
	print ("\nUsage: python script.py <options>")	
	print ("options are:")
	print ("\t-c or --camera (mandatory), camera identifier, example FHAZ")	
	print ("\t-C or --sub-camera (optional), do not download, create videos for the given sub-cameras")
	print ("\t-d or --download-page (optional), download sol page but do not try to download images")
	print ("\t-e or --end-sol (mandatory), the last sol to consider")
	print ("\t-f or --image-frames (optional), how many frames each image lasts")
	print ("\t-h or --help (optional), prints this help")
	print ("\t-s or --start-sol (optional), the start sol to consider")
	exit (1)          

def build(argv):  
	program = curiosity_movie_creator ();
	for i in range (1, len (argv)):
		if argv [i] == '-c' or argv [i] == '--camera':
			i = i + 1
			program.camera = argv [i]
		elif argv [i] == '-e' or argv [i] == '--end-sol':
			i = i + 1
			program.end_sol = int (argv [i]) 
		elif argv [i] == '-f' or argv [i] == '--image-frames':
			i = i + 1
			program.image_frames = int (argv [i]) 
		elif argv [i] == '-s' or argv [i] == '--start-sol':
			i = i + 1
			program.start_sol = int (argv [i]) 
		elif argv [i] == '-C' or argv [i] == '--sub-camera':
			while i + 1 < len (sys.argv):
				i = i + 1
				sub_camera = sys.argv [i]
				if sub_camera [0] != '-':
					program.sub_cameras.append (sub_camera) 
				else:
					break
		elif argv [i] == '-d' or argv [i] == '--download-page':
			program.download_page = True 
		elif argv [i] == '-h' or argv [i] == '--help':
			usage ()
	
	if program.camera is None:
		print('\nCamera argument mandatory')
		usage ()
		
	if program.end_sol is None and len (program.sub_cameras) == 0:
		print('\nEnd sol argument mandatory')
		usage ()

	return program

if __name__ == "__main__":
    build (sys.argv).run ()
